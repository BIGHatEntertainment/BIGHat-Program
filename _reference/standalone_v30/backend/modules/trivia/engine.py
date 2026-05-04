from pydantic import BaseModel
from typing import List, Optional
import uuid

class TriviaRound(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    questions: List[dict]

class TriviaSession:
    def __init__(self, presentation_id: str):
        self.session_id = str(uuid.uuid4())
        self.presentation_id = presentation_id
        self.current_round = 0
        self.scores = {}

    def start_game(self):
        return {"status": "started", "session": self.session_id}
