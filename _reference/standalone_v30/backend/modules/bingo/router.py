from fastapi import APIRouter, HTTPException
from .engine import bingo_manager

router = APIRouter(prefix="/api/bingo", tags=["bingo"])

@router.get("/status")
async def get_status():
    return {"status": "Bingo Engine Active"}

@router.post("/create")
async def create_game(gtype: str = "music"):
    game = bingo_manager.create_game(gtype)
    return {"game_id": game.id, "type": game.type}

@router.get("/songlist/{decade}")
async def get_songs(decade: str):
    # Standalone local fallback songs
    return {
        "success": True,
        "songs": [
            {"number": 1, "title": "Billie Jean", "artist": "Michael Jackson"},
            {"number": 2, "title": "Purple Rain", "artist": "Prince"},
            {"number": 3, "title": "Livin on a Prayer", "artist": "Bon Jovi"}
        ]
    }
