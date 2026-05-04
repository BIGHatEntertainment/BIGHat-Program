import random
import uuid
from typing import List, Optional, Dict
from pydantic import BaseModel

class BingoGame(BaseModel):
    id: str = str(uuid.uuid4())
    type: str = "music" # "traditional" or "music"
    called_items: List[dict] = []
    current_item: Optional[dict] = None
    is_active: bool = False
    
class BingoManager:
    def __init__(self):
        self.active_games = {}
        
    def create_game(self, gtype="music"):
        game = BingoGame(type=gtype)
        self.active_games[game.id] = game
        return game

bingo_manager = BingoManager()
