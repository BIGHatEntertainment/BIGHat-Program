from fastapi import APIRouter, HTTPException, Query
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

def verify_admin(user_name: Optional[str]) -> bool:
    """Verify if the user is authorized to access admin functions"""
    if not user_name:
        return False
    return user_name.lower() in ADMIN_USERS


@router.get("/round-usage")
async def get_all_round_usage(userName: Optional[str] = Query(None)) -> List[Dict]:
    """
    Get all round usage records for admin management.
    Shows which rounds have been used at which locations.
    Requires admin authorization.
    """
    if not verify_admin(userName):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Get all usage records, sorted by date (newest first)
        usage_records = await db.round_usage.find().sort("usedDate", -1).to_list(1000)
        
        result = []
        for record in usage_records:
            # Check if expired
            expires_date = record.get('expiresDate')
            is_expired = expires_date < datetime.utcnow() if isinstance(expires_date, datetime) else False
            
            used_date = record.get('usedDate', '')
            used_date_str = used_date.isoformat() if isinstance(used_date, datetime) else str(used_date)
            
            expires_date_str = expires_date.isoformat() if isinstance(expires_date, datetime) else str(expires_date)
            
            result.append({
                'id': str(record.get('_id', '')),
                'location': record.get('location', ''),
                'locationName': record.get('location', '').split('/')[-1] if record.get('location') else '',
                'roundFile': record.get('roundFile', ''),
                'roundFileName': record.get('roundFileName') or (record.get('roundFile', '').split('/')[-1] if record.get('roundFile') and '/' in record.get('roundFile', '') else record.get('roundFile', '')),
                'roundType': record.get('roundType', ''),
                'roundNumber': record.get('roundNumber', 0),
                'usedDate': used_date_str,
                'expiresDate': expires_date_str,
                'isExpired': is_expired,
                'usedBy': record.get('usedBy', ''),
                'presentationName': record.get('presentationName', ''),
                'presentationId': record.get('presentationId', '')
            })
        
        logger.info(f"Retrieved {len(result)} round usage records")
        return result
    
    except Exception as e:
        logger.error(f"Error fetching round usage: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/round-usage/{usage_id}")
async def release_round(usage_id: str, userName: Optional[str] = Query(None)) -> Dict:
    """
    Release a round back into the selection pool by deleting its usage record.
    Useful for preview/testing or correcting mistakes.
    Requires admin authorization.
    """
    if not verify_admin(userName):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        from bson import ObjectId
        
        # Try to delete by _id (ObjectId)
        try:
            result = await db.round_usage.delete_one({"_id": ObjectId(usage_id)})
        except Exception:
            # If ObjectId fails, try as string id
            result = await db.round_usage.delete_one({"_id": usage_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Usage record not found")
        
        logger.info(f"Released round usage record: {usage_id} by {userName}")
        
        return {
            "success": True,
            "message": "Round released back into selection pool"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error releasing round: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/round-usage/by-presentation/{presentation_id}")
async def release_presentation_rounds(presentation_id: str, userName: Optional[str] = Query(None)) -> Dict:
    """
    Release all rounds from a specific presentation.
    Useful when deleting a test/preview presentation.
    Requires admin authorization.
    """
    if not verify_admin(userName):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        result = await db.round_usage.delete_many({"presentationId": presentation_id})
        
        logger.info(f"Released {result.deleted_count} rounds from presentation {presentation_id} by {userName}")
        
        return {
            "success": True,
            "message": f"Released {result.deleted_count} rounds from presentation",
            "deletedCount": result.deleted_count
        }
    
    except Exception as e:
        logger.error(f"Error releasing presentation rounds: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/round-usage/release-all")
async def release_all_rounds(userName: Optional[str] = Query(None)) -> Dict:
    """
    Release ALL round usage records.
    WARNING: This removes all usage tracking. Use carefully!
    Requires admin authorization.
    """
    if not verify_admin(userName):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        result = await db.round_usage.delete_many({})
        
        logger.warning(f"Released ALL {result.deleted_count} round usage records by {userName}")
        
        return {
            "success": True,
            "message": f"Released all {result.deleted_count} rounds",
            "deletedCount": result.deleted_count
        }
    
    except Exception as e:
        logger.error(f"Error releasing all rounds: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup-expired")
async def cleanup_expired_rounds(userName: Optional[str] = Query(None)) -> Dict:
    """
    Automatically remove all expired round usage records.
    Requires admin authorization.
    """
    if not verify_admin(userName):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        cutoff_date = datetime.utcnow()
        
        result = await db.round_usage.delete_many({
            'expiresDate': {'$lt': cutoff_date}
        })
        
        logger.info(f"Cleaned up {result.deleted_count} expired usage records by {userName}")
        
        return {
            "success": True,
            "message": f"Successfully cleaned up {result.deleted_count} expired records",
            "deletedCount": result.deleted_count
        }
    
    except Exception as e:
        logger.error(f"Error cleaning up expired records: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_admin_stats(userName: Optional[str] = Query(None)) -> Dict:
    """
    Get admin dashboard statistics.
    Requires admin authorization.
    """
    if not verify_admin(userName):
        raise HTTPException(status_code=403, detail="Admin access required")

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

    try:
        total_usage = await _safe_count(db.round_usage)
        total_presentations = await _safe_count(db.trivia_presentations)

        cutoff_date = datetime.utcnow()
        active_usage = await _safe_count(db.round_usage, {'expiresDate': {'$gt': cutoff_date}})
        expired_usage = max(0, total_usage - active_usage)
        
        # v32.0.0-alpha.43: MontyDB (native desktop DB shim) returns a
        # coroutine from `.aggregate()` — not a Motor cursor — so the
        # `.to_list()` chain 500s the endpoint and (per the merchant's
        # debug log) that failure was killing the Trivia Presenter
        # `Promise.all` on the frontend, leaving the presentation list
        # empty. Wrap in a try/except and fall back to Python-side
        # grouping so the desktop always gets a usable stats payload.
        usage_by_type: Dict[str, int] = {}
        try:
            pipeline = [
                {"$group": {"_id": "$roundType", "count": {"$sum": 1}}}
            ]
            agg = db.round_usage.aggregate(pipeline)
            # Motor cursor path
            if hasattr(agg, "to_list"):
                docs = await agg.to_list(100)
            elif hasattr(agg, "__await__"):
                # MontyDB-style: aggregate() returns a coroutine that
                # resolves to a list (or a cursor). Unwrap either way.
                resolved = await agg
                if hasattr(resolved, "to_list"):
                    docs = await resolved.to_list(100)
                else:
                    docs = list(resolved)
            else:
                docs = list(agg)
            usage_by_type = {d["_id"]: d["count"] for d in docs if d.get("_id")}
        except Exception as agg_exc:
            logger.warning("[admin/stats] aggregate fallback: %s", agg_exc)
            # Fallback: pull all usage rows and group in Python. Cheap
            # for a solo desktop DB (thousands of rows at most).
            try:
                all_rows = await db.round_usage.find({}, {"_id": 0, "roundType": 1}).to_list(5000)
                for r in all_rows:
                    rt = r.get("roundType")
                    if rt:
                        usage_by_type[rt] = usage_by_type.get(rt, 0) + 1
            except Exception as fb_exc:
                logger.warning("[admin/stats] fallback grouping failed: %s", fb_exc)

        return {
            "totalUsageRecords": total_usage,
            "activeRecords": active_usage,
            "expiredRecords": expired_usage,
            "totalPresentations": total_presentations,
            "usageByType": usage_by_type,
        }
    
    except Exception as e:
        logger.error(f"Error fetching admin stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


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
