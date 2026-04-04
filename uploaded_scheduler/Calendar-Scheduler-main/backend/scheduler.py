import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime, timezone
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

# API URL for making requests - use internal localhost since scheduler runs in same container
API_URL = os.environ.get('INTERNAL_API_URL', 'http://localhost:8001/api')


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
    Start the scheduler with monthly archive job and email notification jobs
    """
    scheduler = AsyncIOScheduler(timezone='America/Phoenix')  # MST/Arizona time
    
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
    
    logger.info("Scheduler started - Monthly archive (last day 11PM), Friday primary reports (9AM), Monday secondary reports (9AM)")
    
    scheduler.start()
    
    for job_id in ['monthly_archive', 'primary_friday_report', 'secondary_monday_availability']:
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
