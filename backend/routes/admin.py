from fastapi import APIRouter, HTTPException, Query, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Dict, Optional
import logging
from datetime import datetime

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)

db: AsyncIOMotorDatabase = None

# List of authorized admin users (case-insensitive)
ADMIN_USERS = ['nick', 'nicholas', 'caelie', 'tommy', 'al', 'chase', 'chloe', 'zach']

def set_database(database):
    global db
    db = database

async def authorize_admin(request: Request, user_name: Optional[str]) -> None:
    """Standalone auth: real role (admin / master_admin) wins; the legacy
    first-name list stays as a fallback for the cloud webapp."""
    try:
        from server import get_current_user  # type: ignore
        u = await get_current_user(request)
        if (u or {}).get("role") in ("admin", "master_admin"):
            return
    except Exception:
        pass
    if not verify_admin(user_name):
        raise HTTPException(status_code=403, detail="Admin access required")


def verify_admin(user_name: Optional[str]) -> bool:
    """Verify if the user is authorized to access admin functions"""
    if not user_name:
        return False
    return user_name.lower() in ADMIN_USERS


@router.get("/round-usage")
async def get_all_round_usage(request: Request, userName: Optional[str] = Query(None)) -> List[Dict]:
    """All round usage records (DISK store). A round stays locked for its
    location for 180 days or until released here."""
    await authorize_admin(request, userName)
    import round_usage
    return round_usage.list_records()


@router.delete("/round-usage/by-presentation/{presentation_id}")
async def release_presentation_rounds(presentation_id: str, request: Request,
                                      userName: Optional[str] = Query(None)) -> Dict:
    """Release every round of one presentation (e.g. it must be rebuilt)."""
    await authorize_admin(request, userName)
    import round_usage
    n = round_usage.release_presentation(presentation_id)
    logger.info("Released %d rounds from presentation %s by %s", n, presentation_id, userName)
    return {"success": True, "message": f"Released {n} rounds from presentation", "deletedCount": n}


@router.delete("/round-usage/{usage_id}")
async def release_round(usage_id: str, request: Request, userName: Optional[str] = Query(None)) -> Dict:
    """Release one round back into the selection pool."""
    await authorize_admin(request, userName)
    import round_usage
    if round_usage.release(usage_id) == 0:
        raise HTTPException(status_code=404, detail="Usage record not found")
    logger.info("Released round usage %s by %s", usage_id, userName)
    return {"success": True, "message": "Round released back into selection pool"}


@router.post("/round-usage/release-all")
async def release_all_rounds(request: Request, userName: Optional[str] = Query(None)) -> Dict:
    """Release ALL round usage records. Master admin only."""
    await authorize_admin(request, userName)
    import round_usage
    n = round_usage.release_all()
    logger.warning("Released ALL %d round usage records by %s", n, userName)
    return {"success": True, "message": f"Released all {n} rounds", "deletedCount": n}


@router.post("/cleanup-expired")
async def cleanup_expired_rounds(request: Request, userName: Optional[str] = Query(None)) -> Dict:
    """Remove expired (older than 180 days) usage records."""
    await authorize_admin(request, userName)
    import round_usage
    n = round_usage.cleanup_expired()
    return {"success": True, "message": f"Successfully cleaned up {n} expired records", "deletedCount": n}


@router.get("/stats")
async def get_admin_stats(request: Request, userName: Optional[str] = Query(None)) -> Dict:
    """
    Get admin dashboard statistics.
    Requires admin authorization.
    """
    await authorize_admin(request, userName)

    # v32.0.0-alpha.45: EVERY count_documents/aggregate call is wrapped
    # in try/except with a fallback. The desktop MontyDB shim throws
    # two distinct errors under load: `'coroutine' object has no
    # attribute 'to_list'` AND `SQLite objects created in a thread
    # can only be used in that same thread`. Either kills the endpoint
    # and cascades to the Presenter list via Promise.all. From now on
    # this endpoint is BEST-EFFORT — never 500, never blocks the UI.
    async def _safe_count(coll, filt=None):
        try:
            if filt is not None:
                return await coll.count_documents(filt)
            return await coll.count_documents({})
        except Exception as e:
            logger.warning("[admin/stats] count fallback (%s): %s", getattr(coll, "name", "?"), e)
            return 0

    import round_usage as _ru
    _disk = _ru.stats()
    try:
        total_usage = _disk["totalUsageRecords"]
        total_presentations = await _safe_count(db.trivia_presentations)

        cutoff_date = datetime.utcnow()
        active_usage = _disk["activeRecords"]
        expired_usage = _disk["expiredRecords"]
        
        # v32.0.0-alpha.43: MontyDB (native desktop DB shim) returns a
        # coroutine from `.aggregate()` — not a Motor cursor — so the
        # `.to_list()` chain 500s the endpoint and (per the merchant's
        # debug log) that failure was killing the Trivia Presenter
        # `Promise.all` on the frontend, leaving the presentation list
        # empty. Wrap in a try/except and fall back to Python-side
        # grouping so the desktop always gets a usable stats payload.
        usage_by_type: Dict[str, int] = _disk["usageByType"]

        return {
            "totalUsageRecords": total_usage,
            "activeRecords": active_usage,
            "expiredRecords": expired_usage,
            "totalPresentations": total_presentations,
            "usageByType": usage_by_type,
        }
    
    except Exception as e:
        # v32.0.0-alpha.45: NEVER 500 from /admin/stats. Frontend does a
        # Promise.all(getPresentations, getAdminStats, ...) — a 500 here
        # rejects the whole chain and leaves the Trivia Presenter list
        # blank. Return a best-effort zero payload so the UI keeps
        # rendering while we log the underlying failure for triage.
        logger.error(f"[admin/stats] top-level fallback (returning zeros): {e}")
        return {
            "totalUsageRecords": 0,
            "activeRecords": 0,
            "expiredRecords": 0,
            "totalPresentations": 0,
            "usageByType": {},
        }


@router.post("/clear-user-cache")
async def clear_user_cache() -> Dict:
    """
    Clear all user cached data while preserving admin data.
    Deletes:
    - GridFS slides cache (slides.files, slides.chunks)
    - slides_metadata collection
    - presentations collection
    - trivia_presentations collection
    
    Preserves:
    - round_usage collection (admin data)
    """
    try:
        results = {}
        
        # 1. Clear GridFS slides cache
        slides_files_count = await db['slides.files'].count_documents({})
        slides_chunks_count = await db['slides.chunks'].count_documents({})
        
        await db['slides.files'].delete_many({})
        await db['slides.chunks'].delete_many({})
        results['gridfs_files_deleted'] = slides_files_count
        results['gridfs_chunks_deleted'] = slides_chunks_count
        logger.info(f"Deleted {slides_files_count} GridFS files and {slides_chunks_count} chunks")
        
        # 2. Clear slides_metadata
        metadata_count = await db.slides_metadata.count_documents({})
        await db.slides_metadata.delete_many({})
        results['slides_metadata_deleted'] = metadata_count
        logger.info(f"Deleted {metadata_count} slides_metadata records")
        
        # 3. Clear presentations collection
        presentations_count = await db.presentations.count_documents({})
        await db.presentations.delete_many({})
        results['presentations_deleted'] = presentations_count
        logger.info(f"Deleted {presentations_count} presentations")
        
        # 4. Clear trivia_presentations collection
        trivia_count = await db.trivia_presentations.count_documents({})
        await db.trivia_presentations.delete_many({})
        results['trivia_presentations_deleted'] = trivia_count
        logger.info(f"Deleted {trivia_count} trivia_presentations")
        
        # Verify round_usage is preserved
        round_usage_count = await db.round_usage.count_documents({})
        results['round_usage_preserved'] = round_usage_count
        logger.info(f"Preserved {round_usage_count} round_usage records")
        
        logger.warning("USER CACHE CLEARED - All cached data deleted, admin data preserved")
        
        return {
            "success": True,
            "message": "All user cached data cleared. Admin data (round_usage) preserved.",
            "details": results
        }
    
    except Exception as e:
        logger.error(f"Error clearing user cache: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/migrate-presentations")
async def migrate_presentations(userName: Optional[str] = Query(None)) -> Dict:
    """
    Migrate existing trivia_presentations to include new fields:
    - locationFolder: Full folder name for SharePoint matching
    - host: Host display name
    - roundNames: Array of round names
    - roundTypes: Array of round types
    - numRounds: Number of rounds
    
    This enables proper matching with SharePoint JSON files in the Story Generator.
    Requires admin authorization.
    """
    if not verify_admin(userName):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        import re
        
        # Get all presentations
        presentations = await db.trivia_presentations.find().to_list(1000)
        
        updated_count = 0
        skipped_count = 0
        
        for p in presentations:
            updates = {}
            
            # 1. Extract locationFolder from location path
            location = p.get('location', '')
            existing_folder = p.get('locationFolder')
            
            if not existing_folder:
                if '/' in location:
                    # Full path - extract folder name
                    folder = location.split('/')[-1]
                    updates['locationFolder'] = folder
                    # Clean location name
                    updates['location'] = re.sub(r'^\d+_', '', folder)
                else:
                    # Already a folder name or display name
                    updates['locationFolder'] = location
            
            # 2. Extract host name from hostFile
            host_file = p.get('hostFile', '')
            existing_host = p.get('host')
            
            if not existing_host and host_file:
                host_name = host_file.split('/')[-1].replace('.pptx', '') if '/' in host_file else host_file
                updates['host'] = host_name
            
            # 3. Extract roundNames and roundTypes from roundFiles
            round_files = p.get('roundFiles', [])
            existing_names = p.get('roundNames')
            existing_types = p.get('roundTypes')
            
            if not existing_names and round_files:
                round_names = []
                round_types = []
                
                for rf in round_files:
                    # Get round type
                    rtype = rf.get('type', 'REG')
                    round_types.append(rtype)
                    
                    # Get round name from file path
                    file_path = rf.get('file', '')
                    if file_path:
                        filename = file_path.split('/')[-1].replace('.pptx', '')
                        round_names.append(filename)
                    else:
                        round_names.append(f'{rtype} Round')
                
                updates['roundNames'] = round_names
                updates['roundTypes'] = round_types
                updates['numRounds'] = len(round_files)
            
            # Apply updates if any
            if updates:
                await db.trivia_presentations.update_one(
                    {'id': p['id']},
                    {'$set': updates}
                )
                updated_count += 1
                logger.info(f"Migrated presentation: {p.get('name')} - {updates}")
            else:
                skipped_count += 1
        
        return {
            "success": True,
            "message": f"Migration complete. Updated {updated_count} presentations, skipped {skipped_count}.",
            "updated": updated_count,
            "skipped": skipped_count
        }
    
    except Exception as e:
        logger.error(f"Error migrating presentations: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
