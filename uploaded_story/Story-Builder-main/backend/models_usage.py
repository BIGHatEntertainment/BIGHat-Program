from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timedelta
import uuid


class RoundUsage(BaseModel):
    """Track which rounds were used for each location"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    location: str  # Location path
    roundFile: str  # Full path to the round file
    roundType: str  # MC, REG, MISC, MYS, BIG
    usedDate: datetime = Field(default_factory=datetime.utcnow)
    expiresDate: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(days=180))  # 6 months
    usedBy: str  # User name
    presentationId: str  # Reference to presentation


class UsageReport(BaseModel):
    """Report of rounds used in a presentation"""
    presentationId: str
    presentationName: str
    location: str
    locationName: str
    createdBy: str
    createdAt: datetime
    rounds: List[dict]  # List of {type, folder, file, roundNumber}
