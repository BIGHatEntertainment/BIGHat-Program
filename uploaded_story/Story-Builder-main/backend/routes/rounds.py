from fastapi import APIRouter, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
from datetime import datetime, timedelta
from typing import List, Dict
import openpyxl
from io import BytesIO

from sharepoint_service import SharePointService

router = APIRouter(prefix="/rounds", tags=["rounds"])
logger = logging.getLogger(__name__)

db: AsyncIOMotorDatabase = None

def set_database(database):
    global db
    db = database


@router.get("/available")
async def get_available_rounds(location: str):
    """
    Get available rounds from SharePoint folders (REG, MISC, BIG)
    Filters out rounds played in the last 6 months based on admin tab
    """
    try:
        sp = SharePointService()
        
        # Define folder paths for each round type
        base_path = f"01_Trivia/Web App/00_Builder/02_Locations/{location}"
        folders = {
            "REG": f"{base_path}/REG",
            "MISC": f"{base_path}/MISC", 
            "BIG": f"{base_path}/BIG"
        }
        
        # Get recently played rounds from admin tab
        recently_played = await get_recently_played_rounds(sp, location)
        logger.info(f"Recently played rounds (last 6 months): {recently_played}")
        
        available_rounds = {
            "REG": [],
            "MISC": [],
            "BIG": []
        }
        
        # Fetch rounds from each folder
        for round_type, folder_path in folders.items():
            logger.info(f"Fetching {round_type} rounds from: {folder_path}")
            
            try:
                contents = sp.list_folder_contents(folder_path)
                
                for item in contents:
                    # Get Excel files (.xlsx)
                    if item.get('file') and item['name'].endswith('.xlsx'):
                        round_name = item['name'].replace('.xlsx', '')
                        
                        # Check if round was played in last 6 months
                        if round_name not in recently_played:
                            available_rounds[round_type].append({
                                "name": round_name,
                                "path": f"{folder_path}/{item['name']}"
                            })
                
                logger.info(f"Found {len(available_rounds[round_type])} available {round_type} rounds")
                
            except Exception as e:
                logger.error(f"Error fetching {round_type} rounds: {str(e)}")
                # Continue with other folders even if one fails
        
        return available_rounds
        
    except Exception as e:
        logger.error(f"Error getting available rounds: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_recently_played_rounds(sp: SharePointService, location: str) -> List[str]:
    """
    Get list of rounds played in the last 6 months from admin tab
    """
    try:
        # Path to admin Excel file
        admin_file_path = f"01_Trivia/Web App/00_Builder/02_Locations/{location}/Admin/history.xlsx"
        
        logger.info(f"Fetching admin history from: {admin_file_path}")
        
        # Download admin file as bytes
        file_bytes = sp.download_file_to_bytes(admin_file_path)
        
        if not file_bytes:
            logger.warning("No admin history file found, returning empty list")
            return []
        
        # Parse Excel file
        workbook = openpyxl.load_workbook(BytesIO(file_bytes))
        sheet = workbook.active
        
        # Calculate 6 months ago date
        six_months_ago = datetime.now() - timedelta(days=180)
        
        recently_played = []
        
        # Assuming format: Column A = Round Name, Column B = Date Played
        # Skip header row
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if len(row) >= 2:
                round_name = row[0]
                date_played = row[1]
                
                # Check if date is within last 6 months
                if isinstance(date_played, datetime):
                    if date_played >= six_months_ago:
                        recently_played.append(str(round_name))
                elif isinstance(date_played, str):
                    # Try parsing string date
                    try:
                        parsed_date = datetime.strptime(date_played, "%Y-%m-%d")
                        if parsed_date >= six_months_ago:
                            recently_played.append(str(round_name))
                    except:
                        pass
        
        logger.info(f"Found {len(recently_played)} recently played rounds")
        return recently_played
        
    except Exception as e:
        logger.warning(f"Could not load admin history: {str(e)}")
        # Return empty list if admin file doesn't exist
        return []


@router.post("/record-selection")
async def record_round_selection(selection: Dict):
    """
    Record the selected rounds from slot machine to admin history
    """
    try:
        # Store selection in database
        selection['timestamp'] = datetime.utcnow().isoformat()
        
        await db.round_selections.insert_one(selection)
        
        logger.info(f"Recorded round selection: {selection}")
        
        return {"status": "success", "message": "Selection recorded"}
        
    except Exception as e:
        logger.error(f"Error recording selection: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
