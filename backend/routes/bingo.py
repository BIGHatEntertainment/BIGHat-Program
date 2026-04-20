from fastapi import FastAPI, APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import random
import asyncio
import msal
import requests
import io
import pandas as pd

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
# mongo_url handled by main server
# client handled by main server
db = None

def set_database(database):
    global db, manager
    db = database

# Azure/SharePoint Configuration
AZURE_TENANT_ID = os.environ.get('AZURE_TENANT_ID', '')
AZURE_CLIENT_ID = os.environ.get('AZURE_CLIENT_ID', '')
AZURE_CLIENT_SECRET = os.environ.get('AZURE_CLIENT_SECRET', '')
SHAREPOINT_SITE_URL = os.environ.get('SHAREPOINT_SITE_URL', '')

# Create the main app


# Create a router with the /api prefix
router = APIRouter(prefix="/bingo", tags=["bingo"])

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== MODELS ====================

class GameSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    bingo_type: str = "music"  # NEW: "music" or "traditional"
    game_type: str = "regular"  # regular or lightning
    round_type: str = "traditional"  # traditional, 4-corners, 7, blackout
    call_interval: int = 30  # lightning: 10/15, regular: 30/45/60 seconds
    music_decade: str = "1980s"  # 1970s, 1980s, 1990s, 2000s
    preset_mode: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class GameState(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    settings: GameSettings
    called_numbers: List[int] = []
    current_number: Optional[int] = None
    current_song: Optional[Dict] = None  # NEW: For Music Bingo
    called_songs: List[Dict] = []  # NEW: For Music Bingo
    is_active: bool = False
    is_paused: bool = False
    bingo_claimed: bool = False
    winner_name: Optional[str] = None
    round_number: int = 1
    timer_running: bool = False
    volume: float = 0.75
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class GameStateCreate(BaseModel):
    bingo_type: str = "music"  # NEW
    game_type: str = "regular"
    round_type: str = "traditional"
    call_interval: int = 30
    music_decade: str = "1980s"
    preset_mode: bool = False

class SongCall(BaseModel):
    number: int
    title: str
    artist: str

class BingoVerification(BaseModel):
    winner_name: str
    confirmed: bool

class SharePointFolder(BaseModel):
    name: str
    path: str
    is_folder: bool
    size: Optional[int] = None
    modified: Optional[str] = None

# ==================== WEBSOCKET MANAGER ====================

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.game_state: Optional[Dict] = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        if self.game_state:
            await websocket.send_json({"type": "state_update", "data": self.game_state})

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")

    def update_state(self, state: dict):
        self.game_state = state

manager = ConnectionManager()

# ==================== SHAREPOINT SERVICE ====================

class SharePointService:
    def __init__(self):
        self.access_token = None
        self.token_expires = None
        self.site_id = None
        self.drive_id = None

    def get_access_token(self):
        if self.access_token and self.token_expires and datetime.now(timezone.utc) < self.token_expires:
            return self.access_token

        if not all([AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET]):
            logger.warning("SharePoint credentials not configured")
            return None

        try:
            authority = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
            app = msal.ConfidentialClientApplication(
                AZURE_CLIENT_ID,
                authority=authority,
                client_credential=AZURE_CLIENT_SECRET
            )
            result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
            
            if "access_token" in result:
                self.access_token = result["access_token"]
                self.token_expires = datetime.now(timezone.utc).replace(second=0, microsecond=0)
                return self.access_token
            else:
                logger.error(f"Failed to get token: {result.get('error_description', 'Unknown error')}")
                return None
        except Exception as e:
            logger.error(f"SharePoint auth error: {e}")
            return None

    def get_site_and_drive_ids(self):
        """Get site ID and drive ID for the SharePoint site"""
        if self.site_id and self.drive_id:
            return self.site_id, self.drive_id
            
        token = self.get_access_token()
        if not token:
            return None, None

        try:
            headers = {"Authorization": f"Bearer {token}"}
            
            # Get site by hostname - BHEntertainment.sharepoint.com
            hostname = "bhentertainment.sharepoint.com"
            url = f"https://graph.microsoft.com/v1.0/sites/{hostname}:/"
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                self.site_id = response.json().get("id")
                logger.info(f"Got site ID: {self.site_id}")
                
                # Get the default drive (Documents library)
                drive_url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drive"
                drive_response = requests.get(drive_url, headers=headers)
                if drive_response.status_code == 200:
                    self.drive_id = drive_response.json().get("id")
                    logger.info(f"Got drive ID: {self.drive_id}")
                    return self.site_id, self.drive_id
            else:
                logger.error(f"Failed to get site ID: {response.status_code} - {response.text}")
            return None, None
        except Exception as e:
            logger.error(f"Error getting site/drive IDs: {e}")
            return None, None

    def download_excel_file(self, file_path: str) -> Optional[bytes]:
        """Download an Excel file from SharePoint"""
        token = self.get_access_token()
        if not token:
            return None

        site_id, drive_id = self.get_site_and_drive_ids()
        if not site_id or not drive_id:
            return None

        try:
            headers = {"Authorization": f"Bearer {token}"}
            
            # URL encode the path
            encoded_path = file_path.replace(" ", "%20")
            
            # Get file content
            url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{encoded_path}:/content"
            logger.info(f"Downloading file from: {url}")
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                logger.info(f"Successfully downloaded file: {file_path}")
                return response.content
            else:
                logger.error(f"Failed to download file: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            return None

    # Map common decade names to actual SharePoint file names
    DECADE_FILE_MAP = {
        "2000s": "Y2K",
        "y2k": "Y2K",
        "emo": "Emo",
    }

    def get_song_list_from_sharepoint(self, decade: str) -> Optional[List[Dict]]:
        """Fetch and parse the song list Excel file for a specific decade"""
        # Resolve the file name — check mapping first, then use as-is
        file_label = self.DECADE_FILE_MAP.get(decade.lower(), decade)
        file_path = f"03_Bingo/Web App/00_Builder/03_Songs/Bingo List ({file_label}).xlsx"
        
        content = self.download_excel_file(file_path)
        if not content:
            logger.warning(f"Could not download song list for {decade} (file: {file_label}) from SharePoint")
            return None

        try:
            # Parse with no header — the Excel files have no proper header row
            df = pd.read_excel(io.BytesIO(content), engine='openpyxl', header=None)
            logger.info(f"Excel shape: {df.shape}, columns: {df.columns.tolist()}")

            # Log first few rows for debugging
            for i in range(min(3, len(df))):
                logger.info(f"Row {i}: {df.iloc[i].tolist()}")

            # Find columns by inspecting actual data patterns
            num_col = None
            title_col = None
            artist_col = None

            # Strategy: find the column with sequential integers (that's the number column)
            # Then the remaining two text columns are title and artist
            for col_idx in range(len(df.columns)):
                col_data = df[df.columns[col_idx]].dropna()
                if len(col_data) == 0:
                    continue
                # Check if this column is numeric (song numbers)
                try:
                    numeric_vals = pd.to_numeric(col_data, errors='coerce').dropna()
                    if len(numeric_vals) > len(col_data) * 0.7:
                        # Mostly numeric — this is the number column
                        if num_col is None:
                            num_col = df.columns[col_idx]
                            continue
                except Exception:
                    pass
                # Text column — assign to title first, then artist
                if title_col is None:
                    title_col = df.columns[col_idx]
                elif artist_col is None:
                    artist_col = df.columns[col_idx]

            logger.info(f"Detected columns — Number: {num_col}, Title: {title_col}, Artist: {artist_col}")

            songs = []
            for idx, row in df.iterrows():
                try:
                    # Skip rows without a valid number
                    if num_col is not None and pd.notna(row[num_col]):
                        num_val = row[num_col]
                        try:
                            num = int(float(num_val))
                        except (ValueError, TypeError):
                            continue
                    else:
                        continue

                    title = str(row[title_col]).strip() if title_col is not None and pd.notna(row[title_col]) else f"Song {num}"
                    artist = str(row[artist_col]).strip() if artist_col is not None and pd.notna(row[artist_col]) else "Unknown Artist"

                    # Skip invalid entries
                    if title == "nan" or not title:
                        continue
                    # Clean up quoted strings
                    title = title.strip('"').strip('"').strip('"')
                    artist = artist.strip('"').strip('"').strip('"')

                    songs.append({
                        "number": num,
                        "title": title,
                        "artist": artist
                    })
                except Exception as e:
                    logger.error(f"Error parsing row {idx}: {e}")
                    continue

            if songs:
                logger.info(f"Parsed {len(songs)} songs from SharePoint for {decade}")
                logger.info(f"Sample: #{songs[0]['number']} \"{songs[0]['title']}\" by {songs[0]['artist']}")
                return songs
            else:
                logger.warning(f"No songs parsed from SharePoint for {decade}")
                return None
                
        except Exception as e:
            logger.error(f"Error parsing Excel file: {e}")
            return None

    def list_folder(self, folder_path: str) -> List[SharePointFolder]:
        token = self.get_access_token()
        if not token:
            return []

        try:
            headers = {"Authorization": f"Bearer {token}"}
            site_id, drive_id = self.get_site_and_drive_ids()
            if not site_id or not drive_id:
                return []
            
            # List folder contents
            encoded_path = folder_path.replace(" ", "%20")
            items_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{encoded_path}:/children"
            items_response = requests.get(items_url, headers=headers)
            
            if items_response.status_code != 200:
                logger.error(f"Failed to list folder: {items_response.text}")
                return []

            items = []
            for item in items_response.json().get("value", []):
                items.append(SharePointFolder(
                    name=item.get("name", ""),
                    path=f"{folder_path}/{item.get('name', '')}",
                    is_folder="folder" in item,
                    size=item.get("size"),
                    modified=item.get("lastModifiedDateTime")
                ))
            return items
        except Exception as e:
            logger.error(f"Error listing folder: {e}")
            return []

sharepoint_service = SharePointService()

# ==================== BINGO LOGIC ====================

def generate_bingo_numbers() -> List[int]:
    """Generate all 75 bingo numbers (B1-15, I16-30, N31-45, G46-60, O61-75)"""
    return list(range(1, 76))

def get_letter_for_number(num: int) -> str:
    """Get the BINGO letter for a number"""
    if 1 <= num <= 15:
        return "B"
    elif 16 <= num <= 30:
        return "I"
    elif 31 <= num <= 45:
        return "N"
    elif 46 <= num <= 60:
        return "G"
    elif 61 <= num <= 75:
        return "O"
    return ""

# Sample song lists for each decade (fallback if SharePoint not available)
SAMPLE_SONGS = {
    "1970s": [
        {"number": 1, "title": "Stayin' Alive", "artist": "Bee Gees"},
        {"number": 2, "title": "Bohemian Rhapsody", "artist": "Queen"},
        {"number": 3, "title": "Hotel California", "artist": "Eagles"},
        {"number": 4, "title": "Dancing Queen", "artist": "ABBA"},
        {"number": 5, "title": "Don't Stop Me Now", "artist": "Queen"},
        {"number": 6, "title": "September", "artist": "Earth, Wind & Fire"},
        {"number": 7, "title": "I Will Survive", "artist": "Gloria Gaynor"},
        {"number": 8, "title": "Superstition", "artist": "Stevie Wonder"},
        {"number": 9, "title": "Dreams", "artist": "Fleetwood Mac"},
        {"number": 10, "title": "Heart of Glass", "artist": "Blondie"},
        {"number": 11, "title": "Le Freak", "artist": "Chic"},
        {"number": 12, "title": "Y.M.C.A.", "artist": "Village People"},
        {"number": 13, "title": "We Are the Champions", "artist": "Queen"},
        {"number": 14, "title": "Go Your Own Way", "artist": "Fleetwood Mac"},
        {"number": 15, "title": "Boogie Wonderland", "artist": "Earth, Wind & Fire"}
    ],
    "1980s": [
        {"number": 1, "title": "Billie Jean", "artist": "Michael Jackson"},
        {"number": 2, "title": "Sweet Child O' Mine", "artist": "Guns N' Roses"},
        {"number": 3, "title": "Livin' on a Prayer", "artist": "Bon Jovi"},
        {"number": 4, "title": "Take On Me", "artist": "a-ha"},
        {"number": 5, "title": "Don't Stop Believin'", "artist": "Journey"},
        {"number": 6, "title": "Girls Just Want to Have Fun", "artist": "Cyndi Lauper"},
        {"number": 7, "title": "Like a Virgin", "artist": "Madonna"},
        {"number": 8, "title": "Beat It", "artist": "Michael Jackson"},
        {"number": 9, "title": "Every Breath You Take", "artist": "The Police"},
        {"number": 10, "title": "Pour Some Sugar on Me", "artist": "Def Leppard"},
        {"number": 11, "title": "I Love Rock 'n' Roll", "artist": "Joan Jett"},
        {"number": 12, "title": "Jump", "artist": "Van Halen"},
        {"number": 13, "title": "Come On Eileen", "artist": "Dexys Midnight Runners"},
        {"number": 14, "title": "Africa", "artist": "Toto"},
        {"number": 15, "title": "Footloose", "artist": "Kenny Loggins"}
    ],
    "1990s": [
        {"number": 1, "title": "Smells Like Teen Spirit", "artist": "Nirvana"},
        {"number": 2, "title": "...Baby One More Time", "artist": "Britney Spears"},
        {"number": 3, "title": "Wannabe", "artist": "Spice Girls"},
        {"number": 4, "title": "Losing My Religion", "artist": "R.E.M."},
        {"number": 5, "title": "I Want It That Way", "artist": "Backstreet Boys"},
        {"number": 6, "title": "No Diggity", "artist": "Blackstreet"},
        {"number": 7, "title": "Creep", "artist": "TLC"},
        {"number": 8, "title": "Wonderwall", "artist": "Oasis"},
        {"number": 9, "title": "MMMBop", "artist": "Hanson"},
        {"number": 10, "title": "U Can't Touch This", "artist": "MC Hammer"},
        {"number": 11, "title": "Ice Ice Baby", "artist": "Vanilla Ice"},
        {"number": 12, "title": "Livin' La Vida Loca", "artist": "Ricky Martin"},
        {"number": 13, "title": "Believe", "artist": "Cher"},
        {"number": 14, "title": "My Heart Will Go On", "artist": "Celine Dion"},
        {"number": 15, "title": "I Will Always Love You", "artist": "Whitney Houston"}
    ],
    "2000s": [
        {"number": 1, "title": "Crazy in Love", "artist": "Beyoncé"},
        {"number": 2, "title": "Hey Ya!", "artist": "OutKast"},
        {"number": 3, "title": "Yeah!", "artist": "Usher"},
        {"number": 4, "title": "In Da Club", "artist": "50 Cent"},
        {"number": 5, "title": "Since U Been Gone", "artist": "Kelly Clarkson"},
        {"number": 6, "title": "Mr. Brightside", "artist": "The Killers"},
        {"number": 7, "title": "Toxic", "artist": "Britney Spears"},
        {"number": 8, "title": "Gold Digger", "artist": "Kanye West"},
        {"number": 9, "title": "Umbrella", "artist": "Rihanna"},
        {"number": 10, "title": "Poker Face", "artist": "Lady Gaga"},
        {"number": 11, "title": "Single Ladies", "artist": "Beyoncé"},
        {"number": 12, "title": "I Gotta Feeling", "artist": "Black Eyed Peas"},
        {"number": 13, "title": "Crazy", "artist": "Gnarls Barkley"},
        {"number": 14, "title": "SexyBack", "artist": "Justin Timberlake"},
        {"number": 15, "title": "Hips Don't Lie", "artist": "Shakira"}
    ]
}

# In-memory game state
current_game: Optional[GameState] = None
available_numbers: List[int] = []

# ==================== API ROUTES ====================

@router.get("/")
async def root():
    return {"message": "BIG Hat Music Bingo API", "version": "1.0.0"}

@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Music Bingo API"}

# Game Management
@router.post("/game/create", response_model=dict)
async def create_game(settings: GameStateCreate):
    global current_game, available_numbers
    
    game_settings = GameSettings(
        bingo_type=settings.bingo_type,
        game_type=settings.game_type,
        round_type=settings.round_type,
        call_interval=settings.call_interval,
        music_decade=settings.music_decade,
        preset_mode=settings.preset_mode
    )
    
    current_game = GameState(settings=game_settings)
    
    # For traditional bingo, generate numbers
    if settings.bingo_type == "traditional":
        available_numbers = generate_bingo_numbers()
        random.shuffle(available_numbers)
    else:
        available_numbers = []  # Music bingo manages this on frontend
    
    # Store in MongoDB
    game_doc = current_game.model_dump()
    game_doc['created_at'] = game_doc['created_at'].isoformat()
    game_doc['settings']['created_at'] = game_doc['settings']['created_at'].isoformat()
    await db.games.insert_one(game_doc)
    
    state_dict = {
        "id": current_game.id,
        "settings": current_game.settings.model_dump(),
        "called_numbers": current_game.called_numbers,
        "current_number": current_game.current_number,
        "current_song": current_game.current_song,
        "called_songs": current_game.called_songs,
        "is_active": current_game.is_active,
        "is_paused": current_game.is_paused,
        "bingo_claimed": current_game.bingo_claimed,
        "round_number": current_game.round_number,
        "volume": current_game.volume
    }
    
    manager.update_state(state_dict)
    await manager.broadcast({"type": "game_created", "data": state_dict})
    
    return {"success": True, "game": state_dict}

# Song List endpoint (for Music Bingo)
@router.get("/songlist/{decade}")
async def get_song_list(decade: str):
    """Get song list for a specific decade. Fetches from SharePoint first, falls back to sample data."""
    
    # First try to fetch from SharePoint
    songs = sharepoint_service.get_song_list_from_sharepoint(decade)
    
    if songs:
        logger.info(f"Returning {len(songs)} songs from SharePoint for {decade}")
        return {"success": True, "decade": decade, "songs": songs, "source": "sharepoint"}
    
    # Fall back to sample song list
    logger.info(f"Using sample song list for {decade}")
    sample_songs = SAMPLE_SONGS.get(decade, SAMPLE_SONGS.get("1980s"))
    return {"success": True, "decade": decade, "songs": sample_songs, "source": "sample"}

# Call song endpoint (for Music Bingo)
@router.post("/game/call-song")
async def call_song(song: SongCall):
    global current_game
    if not current_game:
        raise HTTPException(status_code=400, detail="No game created")
    if not current_game.is_active:
        raise HTTPException(status_code=400, detail="Game not active")
    
    song_data = {"number": song.number, "title": song.title, "artist": song.artist}
    current_game.current_song = song_data
    current_game.called_songs.append(song_data)
    current_game.called_numbers.append(song.number)
    current_game.current_number = song.number
    
    state_dict = {
        "id": current_game.id,
        "settings": current_game.settings.model_dump(),
        "called_numbers": current_game.called_numbers,
        "current_number": current_game.current_number,
        "current_song": current_game.current_song,
        "called_songs": current_game.called_songs,
        "is_active": current_game.is_active,
        "is_paused": current_game.is_paused,
        "bingo_claimed": current_game.bingo_claimed,
        "round_number": current_game.round_number,
        "volume": current_game.volume
    }
    
    manager.update_state(state_dict)
    await manager.broadcast({
        "type": "song_called",
        "data": state_dict
    })
    
    return {"success": True, "song": song_data}

@router.post("/game/start")
async def start_game():
    global current_game
    if not current_game:
        raise HTTPException(status_code=400, detail="No game created")
    
    current_game.is_active = True
    current_game.is_paused = False
    
    state_dict = {
        "id": current_game.id,
        "settings": current_game.settings.model_dump(),
        "called_numbers": current_game.called_numbers,
        "current_number": current_game.current_number,
        "is_active": current_game.is_active,
        "is_paused": current_game.is_paused,
        "bingo_claimed": current_game.bingo_claimed,
        "round_number": current_game.round_number,
        "volume": current_game.volume
    }
    
    manager.update_state(state_dict)
    await manager.broadcast({"type": "game_started", "data": state_dict})
    
    return {"success": True, "message": "Game started"}

@router.post("/game/call-number")
async def call_number():
    global current_game, available_numbers
    if not current_game:
        raise HTTPException(status_code=400, detail="No game created")
    if not current_game.is_active:
        raise HTTPException(status_code=400, detail="Game not active")
    if current_game.is_paused:
        raise HTTPException(status_code=400, detail="Game is paused")
    if not available_numbers:
        raise HTTPException(status_code=400, detail="All numbers have been called")
    
    # Get next number
    number = available_numbers.pop(0)
    current_game.current_number = number
    current_game.called_numbers.append(number)
    
    letter = get_letter_for_number(number)
    
    state_dict = {
        "id": current_game.id,
        "settings": current_game.settings.model_dump(),
        "called_numbers": current_game.called_numbers,
        "current_number": current_game.current_number,
        "current_letter": letter,
        "is_active": current_game.is_active,
        "is_paused": current_game.is_paused,
        "bingo_claimed": current_game.bingo_claimed,
        "round_number": current_game.round_number,
        "volume": current_game.volume,
        "remaining_numbers": len(available_numbers)
    }
    
    manager.update_state(state_dict)
    await manager.broadcast({
        "type": "number_called",
        "data": state_dict,
        "number": number,
        "letter": letter
    })
    
    return {"success": True, "number": number, "letter": letter, "remaining": len(available_numbers)}

@router.post("/game/pause")
async def pause_game():
    global current_game
    if not current_game:
        raise HTTPException(status_code=400, detail="No game created")
    
    current_game.is_paused = True
    
    state_dict = {
        "id": current_game.id,
        "is_paused": True,
        "is_active": current_game.is_active
    }
    
    await manager.broadcast({"type": "game_paused", "data": state_dict})
    
    return {"success": True, "message": "Game paused"}

@router.post("/game/resume")
async def resume_game():
    global current_game
    if not current_game:
        raise HTTPException(status_code=400, detail="No game created")
    
    current_game.is_paused = False
    current_game.bingo_claimed = False
    
    state_dict = {
        "id": current_game.id,
        "is_paused": False,
        "is_active": current_game.is_active,
        "bingo_claimed": False
    }
    
    await manager.broadcast({"type": "game_resumed", "data": state_dict})
    
    return {"success": True, "message": "Game resumed"}

@router.post("/game/bingo")
async def claim_bingo():
    global current_game
    if not current_game:
        raise HTTPException(status_code=400, detail="No game created")
    
    current_game.is_paused = True
    current_game.bingo_claimed = True
    
    await manager.broadcast({
        "type": "bingo_claimed",
        "data": {"is_paused": True, "bingo_claimed": True}
    })
    
    return {"success": True, "message": "Bingo claimed - game paused for verification"}

@router.post("/game/verify-bingo")
async def verify_bingo(verification: BingoVerification):
    global current_game
    if not current_game:
        raise HTTPException(status_code=400, detail="No game created")
    
    if verification.confirmed:
        current_game.winner_name = verification.winner_name
        await manager.broadcast({
            "type": "bingo_confirmed",
            "data": {
                "winner_name": verification.winner_name,
                "is_paused": True,
                "bingo_claimed": True
            }
        })
        return {"success": True, "message": f"Bingo confirmed! Winner: {verification.winner_name}"}
    else:
        current_game.bingo_claimed = False
        current_game.is_paused = False
        await manager.broadcast({
            "type": "bingo_rejected",
            "data": {"is_paused": False, "bingo_claimed": False}
        })
        return {"success": True, "message": "Bingo rejected - game continues"}

@router.post("/game/end-round")
async def end_round():
    global current_game, available_numbers
    if not current_game:
        raise HTTPException(status_code=400, detail="No game created")
    
    current_game.is_active = False
    current_game.is_paused = False
    
    await manager.broadcast({
        "type": "round_ended",
        "data": {
            "round_number": current_game.round_number,
            "winner_name": current_game.winner_name,
            "called_numbers": current_game.called_numbers
        }
    })
    
    return {"success": True, "message": "Round ended"}

@router.post("/game/new-round")
async def new_round():
    global current_game, available_numbers
    if not current_game:
        raise HTTPException(status_code=400, detail="No game created")
    
    current_game.round_number += 1
    current_game.called_numbers = []
    current_game.current_number = None
    current_game.bingo_claimed = False
    current_game.winner_name = None
    current_game.is_active = False
    current_game.is_paused = False
    
    available_numbers = generate_bingo_numbers()
    random.shuffle(available_numbers)
    
    state_dict = {
        "id": current_game.id,
        "settings": current_game.settings.model_dump(),
        "called_numbers": [],
        "current_number": None,
        "is_active": False,
        "is_paused": False,
        "bingo_claimed": False,
        "round_number": current_game.round_number,
        "volume": current_game.volume
    }
    
    manager.update_state(state_dict)
    await manager.broadcast({"type": "new_round", "data": state_dict})
    
    return {"success": True, "round_number": current_game.round_number}

@router.get("/game/state")
async def get_game_state():
    global current_game, available_numbers
    if not current_game:
        return {"game": None}
    
    return {
        "game": {
            "id": current_game.id,
            "settings": current_game.settings.model_dump(),
            "called_numbers": current_game.called_numbers,
            "current_number": current_game.current_number,
            "current_letter": get_letter_for_number(current_game.current_number) if current_game.current_number else None,
            "current_song": current_game.current_song,
            "called_songs": current_game.called_songs,
            "is_active": current_game.is_active,
            "is_paused": current_game.is_paused,
            "bingo_claimed": current_game.bingo_claimed,
            "winner_name": current_game.winner_name,
            "round_number": current_game.round_number,
            "volume": current_game.volume,
            "remaining_numbers": len(available_numbers)
        }
    }

class VolumeUpdate(BaseModel):
    volume: float

@router.post("/game/volume")
async def set_volume(update: VolumeUpdate):
    global current_game
    if current_game:
        current_game.volume = max(0, min(1, update.volume))
        await manager.broadcast({
            "type": "volume_changed",
            "data": {"volume": current_game.volume}
        })
    return {"success": True, "volume": current_game.volume if current_game else 0.75}

# SharePoint Routes
@router.get("/sharepoint/folders")
async def list_sharepoint_folders(path: str = "Shared Documents/03_Bingo/Web App"):
    folders = sharepoint_service.list_folder(path)
    return {"success": True, "items": [f.model_dump() for f in folders]}

@router.get("/sharepoint/test")
async def test_sharepoint():
    token = sharepoint_service.get_access_token()
    if token:
        site_id, drive_id = sharepoint_service.get_site_and_drive_ids()
        return {"success": True, "has_token": True, "site_id": site_id, "drive_id": drive_id}
    return {"success": False, "has_token": False, "message": "Could not authenticate with SharePoint"}


@router.get("/available-decades")
async def get_available_decades():
    """
    Fetch available music decades from SharePoint by listing 
    Excel files in the 03_Songs folder. Returns only playable decades.
    """
    import re
    try:
        songs_path = "03_Bingo/Web App/00_Builder/03_Songs"
        items = sharepoint_service.list_folder(songs_path)
        
        # Reverse map for file labels back to decade names
        LABEL_TO_DECADE = {
            "1970s": {"id": "1970s", "name": "1970s", "subtitle": "Disco Era"},
            "1980s": {"id": "1980s", "name": "1980s", "subtitle": "Synth Pop"},
            "1990s": {"id": "1990s", "name": "1990s", "subtitle": "Grunge & Pop"},
            "Y2K":   {"id": "2000s", "name": "2000s", "subtitle": "Y2K Hits"},
            "2000s": {"id": "2000s", "name": "2000s", "subtitle": "Y2K Hits"},
            "Emo":   {"id": "emo", "name": "Emo", "subtitle": "Emo & Pop Punk"},
            "2010s": {"id": "2010s", "name": "2010s", "subtitle": "Modern Pop"},
            "Country": {"id": "country", "name": "Country", "subtitle": "Country Hits"},
            "Reggaeton": {"id": "reggaeton", "name": "Reggaeton", "subtitle": "Latin Beats"},
            "R&B":   {"id": "rnb", "name": "R&B", "subtitle": "R&B & Soul"},
            "Hip Hop": {"id": "hiphop", "name": "Hip Hop", "subtitle": "Hip Hop Classics"},
        }
        
        decades = []
        seen = set()
        for item in items:
            name = item.name if hasattr(item, 'name') else str(item.get('name', ''))
            # Match "Bingo List (LABEL).xlsx" pattern
            match = re.search(r'Bingo List \((.+?)\)\.xlsx', name)
            if match:
                label = match.group(1)
                info = LABEL_TO_DECADE.get(label)
                if not info:
                    # Auto-generate for unknown labels
                    info = {"id": label.lower(), "name": label, "subtitle": f"{label} Music"}
                if info["id"] not in seen:
                    decades.append(info)
                    seen.add(info["id"])
        
        logger.info(f"Found {len(decades)} available decades from SharePoint")
        return {"success": True, "decades": decades}
    except Exception as e:
        logger.error(f"Error fetching available decades: {e}")
        # Return defaults as fallback
        return {"success": False, "decades": [
            {"id": "1970s", "name": "1970s", "subtitle": "Disco Era"},
            {"id": "1980s", "name": "1980s", "subtitle": "Synth Pop"},
            {"id": "1990s", "name": "1990s", "subtitle": "Grunge & Pop"},
            {"id": "2000s", "name": "2000s", "subtitle": "Y2K Hits"},
            {"id": "emo", "name": "Emo", "subtitle": "Emo & Pop Punk"},
        ]}


# Bingo Card Downloads from SharePoint
SP_DRIVE_ID_BINGO = "b!vFnSKrOPL02dj2-MZU_EHmAti4Py2yROjNNkPjQrBjDvfYp5Cu28QIG93vJSp4xs"
BINGO_CARDS = {
    "1970s": "01Z4PLCYQFK2X2EFJZG5AJZVWVIS7ZVWDW",
    "1980s": "01Z4PLCYVUNIXKBBUZMJA3AJJNSUEBDWMB",
    "1990s": "01Z4PLCYXTLA6NQWDXYZDZ6XAXL7SN262R",
    "Y2K": "01Z4PLCYQX6DNOIBCVJFHLZC4C6JA6W6XY",
}
BINGO_SENIOR_CARDS = {
    "1970s": "01Z4PLCYVBTDHW3SOCM5FKNGYIMMS2Q3XN",
    "1980s": "01Z4PLCYWFD5JWISBYKNFKPWVY5VD3TR5N",
    "1990s": "01Z4PLCYWVZG5KA3OYEZCZP7WIFQKGGL6L",
    "Y2K": "01Z4PLCYUQYLDJOXCCQBCJGNAC2CQYQ72K",
    "X-Mas": "01Z4PLCYQPHDG4JOCOGNAKS5JJO5OGFFK4",
}
BINGO_SPECIAL_CARDS = {
    "Pop Punk & Emo": "01Z4PLCYX24Y24KVO2EBAKH4XDWPXQYMBA",
    "X-Mas": "01Z4PLCYX22ODIB5XGFVHIHLNYCKWVXMAL",
}

@router.get("/bingo-cards")
async def list_bingo_cards():
    """List available bingo card categories."""
    return {
        "standard": [{"id": k, "name": f"Bingo ({k})"} for k in ["1970s", "1980s", "1990s", "Y2K"]],
        "senior": [{"id": k, "name": f"Senior Bingo ({k})"} for k in BINGO_SENIOR_CARDS.keys()],
        "special": [{"id": k, "name": f"Special: {k}"} for k in BINGO_SPECIAL_CARDS.keys()],
    }

@router.get("/bingo-cards/download/{category}/{decade}")
async def download_bingo_card(category: str, decade: str):
    """Download a bingo card PDF from SharePoint."""
    import httpx
    
    if category == "standard":
        file_id = BINGO_CARDS.get(decade)
    elif category == "senior":
        file_id = BINGO_SENIOR_CARDS.get(decade)
    elif category == "special":
        file_id = BINGO_SPECIAL_CARDS.get(decade)
    else:
        raise HTTPException(status_code=400, detail="Invalid category")
    
    if not file_id:
        raise HTTPException(status_code=404, detail=f"No card found for {category}/{decade}")
    
    tenant = os.environ.get("ROUNDMAKER_TENANT_ID", os.environ.get("AZURE_TENANT_ID", ""))
    cid = os.environ.get("ROUNDMAKER_CLIENT_ID", os.environ.get("AZURE_CLIENT_ID", ""))
    csec = os.environ.get("ROUNDMAKER_CLIENT_SECRET", os.environ.get("AZURE_CLIENT_SECRET", ""))
    
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token", data={
            "grant_type": "client_credentials", "client_id": cid, "client_secret": csec,
            "scope": "https://graph.microsoft.com/.default"
        })
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="SharePoint auth failed")
        token = r.json()["access_token"]
    
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(f"https://graph.microsoft.com/v1.0/drives/{SP_DRIVE_ID_BINGO}/items/{file_id}/content",
            headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 200:
            from fastapi.responses import Response
            return Response(content=r.content, media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="Bingo ({decade}).pdf"'})
        raise HTTPException(status_code=500, detail="Failed to download card")
