from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from core.config_manager import ConfigManager
from core.database import init_db
import core.licensing as licensing
import core.updater as updater

# Modular Routers
from modules.trivia.router import router as trivia_router
from modules.bingo.router import router as bingo_router
from settings_template import SETTINGS_UI_HTML
from modules.scheduler.router import router as scheduler_router
from modules.tools.router import router as tools_router

# HTML Templates
from hub_template import HUB_HTML
from modules.trivia.presenter_logic import TRIVIA_UI
from bingo_template import BINGO_UI_HTML
from scheduler_template import SCHEDULER_UI_HTML
from tools_template import TOOLS_UI_HTML

import os
import bcrypt
import uuid
import json

app = FastAPI(title="BIG Hat Entertainment Hub")
config_mgr = ConfigManager()

# Ensure we have a unique ID for this installation
if not config_mgr.config.get("instance_id"):
    config_mgr.config["instance_id"] = str(uuid.uuid4())
    config_mgr.save_config()

# Static & Module Mounting
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(trivia_router)
app.include_router(bingo_router)
app.include_router(scheduler_router)
app.include_router(tools_router)

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    if config_mgr.is_setup_required():
        # Setup logic is handled in the frontend Wizard
        # For this version, we serve the SETUP_HTML from previous turn
        return HTMLResponse(content=open("setup.html").read()) if os.path.exists("setup.html") else HUB_HTML
    
    if not request.cookies.get("session_token"):
        return HTMLResponse(content="<h2>Please Login</h2>") # Placeholder
        
    return HUB_HTML

@app.get("/api/setup/status")
async def get_setup_status():
    update_info = await updater.check_for_updates()
    return {"config": config_mgr.config, "update": update_info}

@app.post("/api/setup/initialize")
async def initialize_system(setup_data: dict):
    # Setup mapping and master admin
    instance_id = config_mgr.config.get("instance_id")
    config_mgr.config.update({
        "setup_complete": True,
        "settings": setup_data.get("settings", {}),
        "license_status": {
            "key": setup_data.get("license_key"),
            "active_seats": [instance_id]
        },
        "users": [setup_data.get("master_admin")]
    })
    config_mgr.save_config()
    
    response = JSONResponse(content={"status": "success"})
    response.set_cookie(key="session_token", value="active_session", max_age=31536000)
    return response

# UI ROUTES
@app.get("/trivia/present/{pres_id}", response_class=HTMLResponse)
async def present_trivia(pres_id: str): return TRIVIA_UI

@app.get("/bingo/host/{game_id}", response_class=HTMLResponse)
async def host_bingo(game_id: str): return BINGO_UI_HTML

@app.get("/schedule", response_class=HTMLResponse)
async def view_scheduler(): return SCHEDULER_UI_HTML

@app.get("/tools", response_class=HTMLResponse)
async def view_tools(): return TOOLS_UI_HTML

if __name__ == "__main__":
    import uvicorn
    init_db()
    uvicorn.run(app, host="0.0.0.0", port=8000)

@app.get("/api/docs/view")
async def view_docs():
    with open("../DOCUMENTATION.md", "r") as f:
        content = f.read()
    return HTMLResponse(content=f"<html><body style='background:#000e2a; color:white; font-family:sans-serif; padding:50px; line-height:1.6;'><pre style='white-space:pre-wrap;'>{content}</pre></body></html>")

@app.get("/admin/settings", response_class=HTMLResponse)
async def view_settings():
    return SETTINGS_UI_HTML

@app.post("/api/admin/settings/save")
async def save_settings(data: dict):
    config_mgr.config['settings'].update(data.get('settings', {}))
    config_mgr.config['paths'].update(data.get('paths', {}))
    config_mgr.save_config()
    return {"status": "ok"}
