import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from motor.motor_asyncio import AsyncIOMotorClient
import os
import glob
import time
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime, timezone, timedelta
import logging
import httpx

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]
# Native-mode swap: when BIGHAT_NATIVE_MODE=1, use SQLite-backed MontyDB
try:
    from native.db_factory import get_db as _get_native_db, is_native as _is_native_mode
    if _is_native_mode():
        db = _get_native_db()
        logger.info("[NATIVE-MODE] scheduler using MontyDB SQLite backend")
except Exception as _e:
    logger.warning(f"[NATIVE-MODE] scheduler db_factory unavailable: {_e}")

# API URL for making requests - use internal localhost since scheduler runs in same container
API_URL = os.environ.get('INTERNAL_API_URL', 'http://localhost:8001/api')


async def cleanup_generated_assets():
    """Delete generated story videos, scoreboard exports, and temp files older than 24 hours."""
    try:
        now = time.time()
        max_age = 24 * 3600  # 24 hours
        deleted = 0
        
        dirs_to_clean = [
            ROOT_DIR / 'assets' / 'generated',    # Story Generator MP4s
            ROOT_DIR / 'exports',                   # Scoreboard exports
        ]
        # Also clean /tmp/story_videos (QR temp downloads)
        tmp_story = Path('/tmp/story_videos')
        if tmp_story.exists():
            dirs_to_clean.append(tmp_story)
        
        for directory in dirs_to_clean:
            if not directory.exists():
                continue
            for f in directory.iterdir():
                if f.is_file() and f.suffix in ['.mp4', '.png', '.webm', '.jpg']:
                    age = now - f.stat().st_mtime
                    if age > max_age:
                        f.unlink()
                        deleted += 1
        
        if deleted:
            logger.info(f"[Cleanup] Deleted {deleted} generated assets older than 24h")
    except Exception as e:
        logger.error(f"[Cleanup] Error cleaning assets: {e}")


async def retry_pending_cloud_activation():
    """If the SetupWizard completed offline, retry cloud-license activation
    until it succeeds. On success, mirror the cloud response into local
    state and clear the `pending_cloud_activation` flag.

    Safe to run even when not in native mode — the flag will simply never
    be set."""
    try:
        from native.config import config_manager
        from native.hwid import generate_hwid
        from native import cloud_client
        # Avoid circular import by re-implementing the apply logic inline.
        from native.router import _apply_cloud_response_to_local_state
    except ImportError as e:
        logger.warning(f"[CloudRetry] native modules unavailable: {e}")
        return

    cfg = config_manager.config
    lic = cfg.get("license_status", {}) or {}
    if not lic.get("pending_cloud_activation"):
        return
    key = lic.get("key")
    if not key:
        return
    hwid = generate_hwid()
    label = None
    seats = lic.get("active_seats", []) or []
    for s in seats:
        if s.get("hwid") == hwid:
            label = s.get("label")
            break
    resp = await cloud_client.activate(
        license_key=key, hwid=hwid,
        machine_name=label or "BIG Hat",
        email=lic.get("master_admin_email"),
    )
    if not resp.get("ok"):
        if resp.get("error") in ("timeout", "network_error", "server_error"):
            logger.info(f"[CloudRetry] still offline ({resp.get('error')}); will retry next tick")
        else:
            # Authoritative failure — log it but don't keep retrying.
            logger.warning(
                f"[CloudRetry] cloud rejected pending activation: {resp.get('error')}: {resp.get('message')}"
            )
            lic2 = config_manager.config.setdefault("license_status", {})
            lic2["pending_cloud_activation"] = False
            lic2["cloud_activation_error"] = resp.get("error")
            config_manager.save_config()
        return
    _apply_cloud_response_to_local_state(resp, license_key=key, email=lic.get("master_admin_email"))
    lic2 = config_manager.config.setdefault("license_status", {})
    lic2["pending_cloud_activation"] = False
    lic2.pop("cloud_activation_error", None)
    config_manager.save_config()
    logger.info(
        "[CloudRetry] cloud activation succeeded; cleared pending flag "
        f"(owns_standalone={resp.get('owns_standalone')}, "
        f"cloud_library={resp.get('cloud_library_active')})"
    )


async def cleanup_old_events():
    """Hide events older than 10 days by marking them as archived. Preserves payment data."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        result = await db.events.update_many(
            {"date": {"$lt": cutoff}, "archived": {"$ne": True}},
            {"$set": {"archived": True}}
        )
        if result.modified_count:
            logger.info(f"[Cleanup] Archived {result.modified_count} events older than 10 days")
    except Exception as e:
        logger.error(f"[Cleanup] Error archiving events: {e}")


async def create_monthly_archive():
    """
    Create monthly archive on the last day of the month at 11:00 PM MST
    """
    try:
        # Get current month in format YYYY-MM
        now = datetime.now(timezone.utc)
        month = now.strftime('%Y-%m')
        
        logger.info(f"Creating monthly archive for {month}")
        
        # Make API call to create archive
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/reports/monthly/archive",
                params={"month": month},
                timeout=30.0
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Monthly archive created successfully: {result['message']}")
                logger.info(f"Total Income: ${result['archive']['total_income']}")
                logger.info(f"Total Outgoing: ${result['archive']['total_outgoing']}")
                logger.info(f"Net Revenue: ${result['archive']['net_revenue']}")
            elif response.status_code == 400:
                logger.warning(f"Archive already exists for {month}")
            else:
                logger.error(f"Failed to create archive: {response.status_code} - {response.text}")
                
    except Exception as e:
        logger.error(f"Error creating monthly archive: {str(e)}")


def start_scheduler():
    """
    Start the scheduler with monthly archive, email notification, and cleanup jobs
    """
    scheduler = AsyncIOScheduler(timezone='America/Phoenix')  # MST/Arizona time
    
    # Hourly: clean up generated assets older than 24h
    scheduler.add_job(
        cleanup_generated_assets,
        trigger=IntervalTrigger(hours=1),
        id='cleanup_assets',
        name='Cleanup Generated Assets (24h)',
        replace_existing=True
    )

    # Every 4 hours: retry cloud-license activation for installs that
    # completed setup while offline.
    scheduler.add_job(
        retry_pending_cloud_activation,
        trigger=IntervalTrigger(hours=4),
        id='retry_pending_cloud_activation',
        name='Retry Pending Cloud Activation',
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(minutes=2),
    )
    
    # Daily at 3 AM: archive events older than 10 days
    scheduler.add_job(
        cleanup_old_events,
        trigger=CronTrigger(hour=3, minute=0, timezone='America/Phoenix'),
        id='cleanup_events',
        name='Archive Old Events (10d)',
        replace_existing=True
    )
    
    # Run on the last day of every month at 11:00 PM MST
    scheduler.add_job(
        create_monthly_archive,
        trigger=CronTrigger(
            hour=23,
            minute=0,
            day='last',
            timezone='America/Phoenix'
        ),
        id='monthly_archive',
        name='Create Monthly Archive',
        replace_existing=True
    )
    
    # Friday 9:00 AM MST — Primary host venue reports
    scheduler.add_job(
        send_primary_reports_job,
        trigger=CronTrigger(
            day_of_week='fri',
            hour=9,
            minute=0,
            timezone='America/Phoenix'
        ),
        id='primary_friday_report',
        name='Friday Primary Reports',
        replace_existing=True
    )
    
    # Monday 9:00 AM MST — Secondary host availability emails
    scheduler.add_job(
        send_secondary_availability_job,
        trigger=CronTrigger(
            day_of_week='mon',
            hour=9,
            minute=0,
            timezone='America/Phoenix'
        ),
        id='secondary_monday_availability',
        name='Monday Secondary Availability',
        replace_existing=True
    )
    
    logger.info("Scheduler started — Asset cleanup (hourly), Event archive (3AM daily), Monthly archive (last day 11PM), Friday reports (9AM), Monday reports (9AM)")
    
    scheduler.start()
    
    for job_id in ['cleanup_assets', 'retry_pending_cloud_activation', 'cleanup_events', 'monthly_archive', 'primary_friday_report', 'secondary_monday_availability']:
        try:
            job = scheduler.get_job(job_id)
            if job:
                logger.info(f"  {job.name} next run: {job.next_run_time}")
        except Exception as e:
            logger.warning(f"Could not get next run time for {job_id}: {e}")
    
    return scheduler


async def send_primary_reports_job():
    """Wrapper for the scheduled Friday primary report emails."""
    try:
        from notifications import send_primary_friday_reports
        result = await send_primary_friday_reports()
        logger.info(f"Primary reports job complete: {result}")
    except Exception as e:
        logger.error(f"Error in primary reports job: {e}")


async def send_secondary_availability_job():
    """Wrapper for the scheduled Monday secondary availability emails."""
    try:
        from notifications import send_secondary_monday_availability
        result = await send_secondary_monday_availability()
        logger.info(f"Secondary availability job complete: {result}")
    except Exception as e:
        logger.error(f"Error in secondary availability job: {e}")
