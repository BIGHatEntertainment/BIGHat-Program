"""
Scores Routes - Save/list/delete trivia scores on SharePoint
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Optional
import logging
import json
import os
import re
from datetime import datetime, timezone

router = APIRouter(prefix="/scores", tags=["scores"])
logger = logging.getLogger(__name__)

db = None
def set_database(database):
    global db
    db = database

SP_DRIVE_ID = "b!vFnSKrOPL02dj2-MZU_EHmAti4Py2yROjNNkPjQrBjDvfYp5Cu28QIG93vJSp4xs"
SP_SCORES_FOLDER_ID = "01Z4PLCYTDUSDUZ2ONIZFYVB54TIOLWSRQ"

async def _get_sp_token():
    import httpx
    tenant = os.environ.get("ROUNDMAKER_TENANT_ID", os.environ.get("AZURE_TENANT_ID", ""))
    cid = os.environ.get("ROUNDMAKER_CLIENT_ID", os.environ.get("AZURE_CLIENT_ID", ""))
    csec = os.environ.get("ROUNDMAKER_CLIENT_SECRET", os.environ.get("AZURE_CLIENT_SECRET", ""))
    if not all([tenant, cid, csec]): return None
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token", data={
            "grant_type": "client_credentials", "client_id": cid, "client_secret": csec,
            "scope": "https://graph.microsoft.com/.default"
        })
        return r.json()["access_token"] if r.status_code == 200 else None

async def _find_or_create_subfolder(token, location_name):
    """Find or create a location subfolder in the Scores folder using fuzzy matching."""
    import httpx
    headers = {"Authorization": f"Bearer {token}"}
    
    # List existing subfolders
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"https://graph.microsoft.com/v1.0/drives/{SP_DRIVE_ID}/items/{SP_SCORES_FOLDER_ID}/children", headers=headers)
        if r.status_code != 200:
            return None
        existing = r.json().get("value", [])
    
    # Clean the location name
    clean = re.sub(r'^\d+_', '', location_name).strip()
    
    # Fuzzy match against existing folders
    for item in existing:
        if not item.get("folder"):
            continue
        folder_name = item["name"]
        # Match if names are similar (case-insensitive, ignore prefixes)
        folder_clean = re.sub(r'^\d+_', '', folder_name).strip()
        if folder_clean.lower() == clean.lower() or clean.lower() in folder_clean.lower() or folder_clean.lower() in clean.lower():
            logger.info(f"Matched existing folder: '{folder_name}' for '{location_name}'")
            return item["id"], folder_name
    
    # No match — create new folder
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"https://graph.microsoft.com/v1.0/drives/{SP_DRIVE_ID}/items/{SP_SCORES_FOLDER_ID}/children",
            headers={**headers, "Content-Type": "application/json"},
            json={"name": clean, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}
        )
        if r.status_code in (200, 201):
            logger.info(f"Created new folder: '{clean}'")
            return r.json()["id"], clean
        elif r.status_code == 409:
            # Race condition — folder was just created, list again
            r2 = await client.get(f"https://graph.microsoft.com/v1.0/drives/{SP_DRIVE_ID}/items/{SP_SCORES_FOLDER_ID}/children", headers=headers)
            for item in r2.json().get("value", []):
                if item.get("name", "").lower() == clean.lower():
                    return item["id"], item["name"]
    
    return None, None

# Models
class TeamScore(BaseModel):
    name: str
    swag: str = ""
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
    """Save trivia scores as JSON to SharePoint, organized by location."""
    try:
        token = await _get_sp_token()
        if not token:
            raise HTTPException(status_code=500, detail="SharePoint authentication failed")

        # Build the JSON data
        scores_data = {
            "location": request.locationName,
            "presentationName": request.presentationName,
            "date": request.presentationDate,
            "presentationId": request.presentationId,
            "savedAt": datetime.now(timezone.utc).isoformat(),
            "rounds": [{"label": r.label, "multiplier": r.multiplier} for r in request.rounds],
            "rankings": [],
            "teams": []
        }

        for idx, team in enumerate(request.teams):
            scores_data["teams"].append({
                "rank": idx + 1, "name": team.name, "swag": team.swag,
                "roundScores": team.roundScores, "total": team.total
            })
            if idx < 3:
                scores_data["rankings"].append({"place": idx + 1, "team": team.name, "score": team.total})

        json_content = json.dumps(scores_data, indent=2).encode('utf-8')

        # Find or create the location subfolder
        subfolder_id, folder_name = await _find_or_create_subfolder(token, request.locationName)
        if not subfolder_id:
            raise HTTPException(status_code=500, detail=f"Could not create/find folder for: {request.locationName}")

        # Upload JSON file
        date_clean = request.presentationDate.replace('/', '-').replace(' ', '_')
        filename = f"{folder_name}_{date_clean}.json"
        
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.put(
                f"https://graph.microsoft.com/v1.0/drives/{SP_DRIVE_ID}/items/{subfolder_id}:/{filename}:/content",
                content=json_content,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            )
            if r.status_code not in (200, 201):
                raise HTTPException(status_code=500, detail="Failed to upload scores file")

        # Also save to DB for the admin tab
        if db is not None:
            scores_data["_filename"] = filename
            scores_data["_folder"] = folder_name
            scores_data["_subfolderId"] = subfolder_id
            await db.trivia_scores.insert_one(scores_data)

        # Mark presentation as completed for auto-hide
        if request.presentationId and db is not None:
            from datetime import timedelta
            auto_hide = datetime.now(timezone.utc) + timedelta(days=3)
            await db.trivia_presentations.update_one(
                {"id": request.presentationId},
                {"$set": {"completedAt": datetime.now(timezone.utc).isoformat(), "autoHideAt": auto_hide.isoformat()}}
            )
            await db.presentations.update_one(
                {"id": request.presentationId},
                {"$set": {"completedAt": datetime.now(timezone.utc).isoformat(), "autoHideAt": auto_hide.isoformat()}}
            )

        logger.info(f"Scores saved: {folder_name}/{filename} ({len(request.teams)} teams)")
        return {"success": True, "path": f"{folder_name}/{filename}", "teams": len(request.teams),
                "topTeam": request.teams[0].name if request.teams else None}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving scores: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files")
async def list_score_files():
    """List all score files from SharePoint organized by location."""
    try:
        token = await _get_sp_token()
        if not token:
            raise HTTPException(status_code=500, detail="SharePoint auth failed")
        
        import httpx
        headers = {"Authorization": f"Bearer {token}"}
        result = []
        
        async with httpx.AsyncClient(timeout=15) as client:
            # List location subfolders
            r = await client.get(f"https://graph.microsoft.com/v1.0/drives/{SP_DRIVE_ID}/items/{SP_SCORES_FOLDER_ID}/children", headers=headers)
            if r.status_code != 200:
                return []
            
            for folder in r.json().get("value", []):
                if not folder.get("folder"):
                    continue
                # List files in each subfolder
                r2 = await client.get(f"https://graph.microsoft.com/v1.0/drives/{SP_DRIVE_ID}/items/{folder['id']}/children", headers=headers)
                files = []
                if r2.status_code == 200:
                    for f in r2.json().get("value", []):
                        if f.get("name", "").endswith(".json"):
                            files.append({"name": f["name"], "id": f["id"], "size": f.get("size", 0),
                                          "modified": f.get("lastModifiedDateTime", "")})
                result.append({"location": folder["name"], "folderId": folder["id"], "fileCount": len(files), "files": files})
        
        return result
    except Exception as e:
        logger.error(f"Error listing score files: {e}")
        return []

@router.delete("/files/{file_id}")
async def delete_score_file(file_id: str):
    """Delete a score file from SharePoint."""
    try:
        token = await _get_sp_token()
        if not token:
            raise HTTPException(status_code=500, detail="SharePoint auth failed")
        
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.delete(f"https://graph.microsoft.com/v1.0/drives/{SP_DRIVE_ID}/items/{file_id}",
                headers={"Authorization": f"Bearer {token}"})
            if r.status_code in (200, 204):
                return {"success": True}
            raise HTTPException(status_code=r.status_code, detail="Failed to delete file")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
