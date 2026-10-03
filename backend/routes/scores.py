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
    """Save one night's trivia scores ON THIS PC (Documents + AppData copy).
    SharePoint is an optional extra: if it is set up it also gets a copy, but a SharePoint problem never loses the scores."""
    from native import scores_store
    scores_data = {
        "location": request.locationName,
        "presentationName": request.presentationName,
        "date": request.presentationDate,
        "presentationId": request.presentationId,
        "savedAt": datetime.now(timezone.utc).isoformat(),
        "rounds": [{"label": r.label, "multiplier": r.multiplier} for r in request.rounds],
        "rankings": [],
        "teams": [],
    }
    for idx, team in enumerate(request.teams):
        scores_data["teams"].append({"rank": idx + 1, "name": team.name, "swag": team.swag,
                                     "roundScores": team.roundScores, "total": team.total})
        if idx < 3:
            scores_data["rankings"].append({"place": idx + 1, "team": team.name, "score": team.total})

    try:
        saved = scores_store.save(scores_data)
    except OSError as e:
        logger.error(f"Could not write scores to disk: {e}")
        raise HTTPException(status_code=500, detail=f"Could not save scores on this PC: {e}")

    # Optional SharePoint copy (cloud builds only). Never fails the save.
    shared = False
    try:
        token = await _get_sp_token()
        if token:
            subfolder_id, folder_name = await _find_or_create_subfolder(token, request.locationName)
            if subfolder_id:
                import httpx
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.put(
                        f"https://graph.microsoft.com/v1.0/drives/{SP_DRIVE_ID}/items/{subfolder_id}:/{saved['filename']}:/content",
                        content=json.dumps(scores_data, indent=2).encode("utf-8"),
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                    shared = r.status_code in (200, 201)
    except Exception as e:                                     # noqa: BLE001
        logger.info(f"SharePoint copy skipped: {e}")

    try:
        if db is not None:
            await db.trivia_scores.insert_one({**scores_data, "_filename": saved["filename"], "_folder": saved["folder"]})
            if request.presentationId:
                from datetime import timedelta
                now = datetime.now(timezone.utc)
                done = {"completedAt": now.isoformat(), "autoHideAt": (now + timedelta(days=3)).isoformat()}
                await db.trivia_presentations.update_one({"id": request.presentationId}, {"$set": done})
                await db.presentations.update_one({"id": request.presentationId}, {"$set": done})
    except Exception as e:                                     # noqa: BLE001
        logger.warning(f"Scores saved to disk but the database note failed: {e}")

    logger.info(f"Scores saved: {saved['path']} ({len(request.teams)} teams, sharepoint={shared})")
    return {"success": True, "path": saved["path"], "teams": len(request.teams),
            "topTeam": request.teams[0].name if request.teams else None, "sharedToSharePoint": shared}


@router.get("/files")
async def list_score_files():
    """List the score files saved on this PC, grouped by location."""
    from native import scores_store
    return scores_store.list_files()


@router.get("/files/{location}/{filename}")
async def read_score_file(location: str, filename: str):
    from native import scores_store
    data = scores_store.read(f"{location}/{filename}")
    if data is None:
        raise HTTPException(status_code=404, detail="Score file not found")
    return data


@router.delete("/files/{location}/{filename}")
async def delete_score_file(location: str, filename: str):
    """Delete a saved score file (both the Documents copy and the AppData copy)."""
    from native import scores_store
    if not scores_store.delete(f"{location}/{filename}"):
        raise HTTPException(status_code=404, detail="Score file not found")
    return {"success": True}
