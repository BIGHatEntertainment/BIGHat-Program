"""Background scheduler for Canva sync jobs"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
import os

logger = logging.getLogger(__name__)

# Create scheduler instance
scheduler = AsyncIOScheduler()


def setup_scheduler():
    """Setup the scheduler with all jobs"""
    # Import here to avoid circular imports
    from routes.canva import sync_sponsor_images
    
    # Get sync time from env (default 6 AM MST = 13:00 UTC)
    # MST is UTC-7, so 6 AM MST = 13:00 UTC
    sync_hour_utc = int(os.environ.get("CANVA_SYNC_HOUR_UTC", "13"))
    sync_minute = int(os.environ.get("CANVA_SYNC_MINUTE", "0"))
    
    # Add daily sync job
    scheduler.add_job(
        sync_sponsor_images,
        CronTrigger(hour=sync_hour_utc, minute=sync_minute, timezone="UTC"),
        id="daily_canva_sync",
        name="Daily Canva Sync at 6 AM MST",
        args=["automatic"],
        replace_existing=True
    )
    
    logger.info(f"Scheduled daily Canva sync at {sync_hour_utc}:{sync_minute:02d} UTC (6 AM MST)")


def start_scheduler():
    """Start the scheduler"""
    if not scheduler.running:
        setup_scheduler()
        scheduler.start()
        logger.info("Scheduler started")


def stop_scheduler():
    """Stop the scheduler"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
