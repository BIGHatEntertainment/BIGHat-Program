from fastapi import APIRouter, HTTPException
from core.config_manager import ConfigManager
import os

router = APIRouter(prefix="/api/trivia", tags=["trivia"])
config_mgr = ConfigManager()

@router.get("/rounds/source")
async def get_trivia_source():
    settings = config_mgr.config.get("settings", {})
    source = settings.get("trivia_source", "local")
    sub_active = settings.get("cloud_subscription_active", False)
    
    # Auto-fallback logic
    if source == "cloud" and not sub_active:
        return {"active_source": "local", "status": "fallback_triggered"}
        
    return {"active_source": source, "path": config_mgr.config['paths'].get('local_trivia')}

@router.get("/local-files")
async def list_local_rounds():
    path = config_mgr.config['paths'].get('local_trivia', 'C:/BIG Hat/data/trivia')
    if not os.path.exists(path):
        return {"error": "Path not found", "path": path}
    files = [f for f in os.listdir(path) if f.endswith('.pptx')]
    return {"rounds": files}
