"""
Scores Routes - API endpoints for saving trivia scores to SharePoint
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import logging
import json
import os
import requests

from sharepoint_service import SharePointService

router = APIRouter(prefix="/scores", tags=["scores"])
logger = logging.getLogger(__name__)

# SharePoint sharing URL for the scores folder
SCORES_SHARING_URL = "https://bhentertainment.sharepoint.com/:f:/g/IgBjpIdM6c1GS4qHvJocu0owAWo1ZLe-TIVZAscu0PNNaWg?e=RO42U4"
SHAREPOINT_TIMEOUT = 30


class TeamScore(BaseModel):
    name: str
    swag: str = ''
    roundScores: List[int] = []
    total: int = 0


class RoundConfig(BaseModel):
    label: str
    multiplier: int = 1


class SaveScoresRequest(BaseModel):
    locationName: str
    presentationName: str
    presentationDate: str
    teams: List[TeamScore]
    rounds: List[RoundConfig]
    presentationId: Optional[str] = None


@router.post("/save")
async def save_scores(request: SaveScoresRequest):
    """
    Save trivia scores as a JSON file to SharePoint, organized by location.
    """
    try:
        sp = SharePointService()

        # Build the JSON data
        scores_data = {
            "location": request.locationName,
            "presentationName": request.presentationName,
            "date": request.presentationDate,
            "presentationId": request.presentationId,
            "rounds": [{"label": r.label, "multiplier": r.multiplier} for r in request.rounds],
            "rankings": [],
            "teams": []
        }

        for idx, team in enumerate(request.teams):
            team_data = {
                "rank": idx + 1,
                "name": team.name,
                "swag": team.swag,
                "roundScores": team.roundScores,
                "total": team.total
            }
            scores_data["teams"].append(team_data)
            if idx < 3:
                scores_data["rankings"].append({
                    "place": idx + 1,
                    "team": team.name,
                    "score": team.total
                })

        json_content = json.dumps(scores_data, indent=2).encode('utf-8')

        # Resolve the sharing URL to get the drive info
        folder_info = sp.get_driveitem_info_from_sharing_url(SCORES_SHARING_URL)

        if not folder_info or not folder_info.get('id'):
            logger.error("Could not resolve SharePoint scores folder from sharing URL")
            raise HTTPException(status_code=500, detail="Could not access SharePoint scores folder")

        drive_id = folder_info['driveId']
        folder_id = folder_info['id']

        # Clean location name for folder — strip numeric prefix (e.g., "01_Monkey Pants" -> "Monkey Pants")
        import re
        location_clean = re.sub(r'^\d+_', '', request.locationName).replace('/', '_').strip()
        # Clean date for filename
        date_clean = request.presentationDate.replace('/', '-')
        filename = f"{location_clean}_{date_clean}.json"

        # Upload: create location subfolder and file using Graph API
        token = sp.get_access_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        # Create location subfolder if it doesn't exist (reuse existing)
        create_folder_url = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{folder_id}/children'
        folder_payload = {
            "name": location_clean,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail"
        }
        folder_resp = requests.post(create_folder_url, headers=headers, json=folder_payload, timeout=SHAREPOINT_TIMEOUT)

        # Get subfolder ID (either from creation or it already exists)
        subfolder_id = None
        if folder_resp.status_code in [200, 201]:
            subfolder_id = folder_resp.json().get('id')
        elif folder_resp.status_code == 409:
            # Folder already exists — list children to find it
            list_url = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{folder_id}/children'
            list_resp = requests.get(list_url, headers={'Authorization': f'Bearer {token}'}, timeout=SHAREPOINT_TIMEOUT)
            if list_resp.status_code == 200:
                for item in list_resp.json().get('value', []):
                    if item.get('name') == location_clean and item.get('folder') is not None:
                        subfolder_id = item['id']
                        break

        if not subfolder_id:
            logger.error(f"Could not create/find subfolder '{location_clean}': {folder_resp.status_code} {folder_resp.text[:200]}")
            raise HTTPException(status_code=500, detail=f"Could not create location folder: {location_clean}")

        # Upload the JSON file into the subfolder
        upload_url = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{subfolder_id}:/{filename}:/content'
        upload_headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        upload_resp = requests.put(upload_url, headers=upload_headers, data=json_content, timeout=SHAREPOINT_TIMEOUT)

        if upload_resp.status_code not in [200, 201]:
            logger.error(f"Failed to upload scores: {upload_resp.status_code} {upload_resp.text[:200]}")
            raise HTTPException(status_code=500, detail="Failed to upload scores file")

        logger.info(f"✅ Scores saved: {location_clean}/{filename} ({len(request.teams)} teams)")

        return {
            "success": True,
            "path": f"{location_clean}/{filename}",
            "teams": len(request.teams),
            "topTeam": request.teams[0].name if request.teams else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving scores: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
