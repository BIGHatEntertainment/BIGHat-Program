from fastapi import APIRouter, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Dict
import logging
from datetime import datetime

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)

db: AsyncIOMotorDatabase = None

def set_database(database):
    global db
    db = database


@router.get("/round-usage")
async def get_all_round_usage() -> List[Dict]:
    """
    Get all round usage records for admin management.
    Shows which rounds have been used at which locations.
    """
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
async def release_round(usage_id: str) -> Dict:
    """
    Release a round back into the selection pool by deleting its usage record.
    Useful for preview/testing or correcting mistakes.
    """
    try:
        from bson import ObjectId
        
        # Try to delete by _id (ObjectId)
        try:
            result = await db.round_usage.delete_one({"_id": ObjectId(usage_id)})
        except:
            # If ObjectId fails, try as string id
            result = await db.round_usage.delete_one({"_id": usage_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Usage record not found")
        
        logger.info(f"Released round usage record: {usage_id}")
        
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
async def release_presentation_rounds(presentation_id: str) -> Dict:
    """
    Release all rounds from a specific presentation.
    Useful when deleting a test/preview presentation.
    """
    try:
        result = await db.round_usage.delete_many({"presentationId": presentation_id})
        
        logger.info(f"Released {result.deleted_count} rounds from presentation {presentation_id}")
        
        return {
            "success": True,
            "message": f"Released {result.deleted_count} rounds from presentation",
            "deletedCount": result.deleted_count
        }
    
    except Exception as e:
        logger.error(f"Error releasing presentation rounds: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/round-usage/release-all")
async def release_all_rounds() -> Dict:
    """
    Release ALL round usage records.
    WARNING: This removes all usage tracking. Use carefully!
    """
    try:
        result = await db.round_usage.delete_many({})
        
        logger.warning(f"Released ALL {result.deleted_count} round usage records")
        
        return {
            "success": True,
            "message": f"Released all {result.deleted_count} rounds",
            "deletedCount": result.deleted_count
        }
    
    except Exception as e:
        logger.error(f"Error releasing all rounds: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup-expired")
async def cleanup_expired_rounds() -> Dict:
    """
    Automatically remove all expired round usage records.
    """
    try:
        cutoff_date = datetime.utcnow()
        
        result = await db.round_usage.delete_many({
            'expiresDate': {'$lt': cutoff_date}
        })
        
        logger.info(f"Cleaned up {result.deleted_count} expired usage records")
        
        return {
            "success": True,
            "message": f"Successfully cleaned up {result.deleted_count} expired records",
            "deletedCount": result.deleted_count
        }
    
    except Exception as e:
        logger.error(f"Error cleaning up expired records: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_admin_stats() -> Dict:
    """
    Get admin dashboard statistics.
    """
    try:
        total_usage = await db.round_usage.count_documents({})
        total_presentations = await db.trivia_presentations.count_documents({})
        
        cutoff_date = datetime.utcnow()
        active_usage = await db.round_usage.count_documents({
            'expiresDate': {'$gt': cutoff_date}
        })
        expired_usage = total_usage - active_usage
        
        # Get usage by round type
        pipeline = [
            {"$group": {
                "_id": "$roundType",
                "count": {"$sum": 1}
            }}
        ]
        usage_by_type = await db.round_usage.aggregate(pipeline).to_list(100)
        
        return {
            "totalUsageRecords": total_usage,
            "activeRecords": active_usage,
            "expiredRecords": expired_usage,
            "totalPresentations": total_presentations,
            "usageByType": {item['_id']: item['count'] for item in usage_by_type if item['_id']}
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
