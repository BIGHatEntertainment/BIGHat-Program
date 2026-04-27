"""
Error tracking log — indexes issues to avoid repeating them.
Stored in MongoDB 'error_log' collection.
"""
import logging
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

db = None

def set_database(database):
    global db
    db = database

async def log_error(component: str, error_type: str, detail: str, resolution: str = ""):
    """Log an error with component, type, detail, and optional resolution."""
    if db is None:
        logger.warning(f"Error log DB not set: [{component}] {error_type}: {detail}")
        return
    doc = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "component": component,
        "error_type": error_type,
        "detail": detail,
        "resolution": resolution,
        "resolved": bool(resolution),
    }
    await db.error_log.insert_one(doc)
    logger.error(f"[ERROR_LOG] [{component}] {error_type}: {detail}")

async def get_error_log(limit=50):
    """Get recent errors."""
    if db is None:
        return []
    errors = await db.error_log.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return errors

async def log_resolution(error_type: str, resolution: str):
    """Mark errors of a type as resolved."""
    if db is None:
        return
    await db.error_log.update_many(
        {"error_type": error_type, "resolved": False},
        {"$set": {"resolved": True, "resolution": resolution, "resolved_at": datetime.now(timezone.utc).isoformat()}}
    )
