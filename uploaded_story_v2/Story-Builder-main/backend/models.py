from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import uuid


class Element(BaseModel):
    id: str = Field(default_factory=lambda: f"elem-{uuid.uuid4()}")
    type: str  # 'text' | 'image' | 'shape'
    content: Optional[str] = None
    x: int
    y: int
    width: int
    height: int
    fontSize: Optional[int] = None
    fontWeight: Optional[str] = None
    color: Optional[str] = None
    textAlign: Optional[str] = None
    fontFamily: Optional[str] = None
    lineHeight: Optional[float] = None
    src: Optional[str] = None  # for images


class Slide(BaseModel):
    id: str = Field(default_factory=lambda: f"slide-{uuid.uuid4()}")
    order: int
    background: str
    elements: List[Element]
    metadata: Optional[dict] = None


class Presentation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    createdBy: str
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    slides: List[Slide]


class PresentationCreate(BaseModel):
    name: str
    createdBy: str
    slides: Optional[List[Slide]] = None


class PresentationUpdate(BaseModel):
    name: Optional[str] = None
    slides: Optional[List[Slide]] = None


class TriviaImportRequest(BaseModel):
    userName: str
    host: str  # Host file path
    location: str  # Location folder path
    numRounds: int  # 5 or 6
    rounds: List[str]  # List of individual round file paths (not folders)
    roundTypes: Optional[List[str]] = None  # List of round types (MC, REG, MISC, MYS, BIG)
    roundNames: Optional[List[str]] = None  # List of round display names
    presentationName: Optional[str] = None


class TriviaPresentation(BaseModel):
    """Lightweight trivia presentation - stores file references, not images"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    createdBy: str
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    location: str  # Location folder path
    hostFile: str  # Host file path
    locationFile: str  # Location intro file path
    roundFiles: List[dict]  # [{order, type, file}]
    sponsorFiles: List[str]  # Sponsor file paths
    totalSlides: int  # Estimated number of slides
