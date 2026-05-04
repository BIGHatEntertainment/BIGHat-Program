from fastapi import APIRouter, HTTPException
import os

router = APIRouter(prefix="/api/tools", tags=["tools"])

@router.get("/resources")
async def get_resources():
    return [
        {"name": "Trivia Answer Sheet", "url": "/static/resources/trivia-answer-sheet.pdf"},
        {"name": "Multiple Choice Sheet", "url": "/static/resources/trivia-multiple-choice.pdf"},
        {"name": "Tie Breaker Sheet", "url": "/static/resources/trivia-tie-breaker.pdf"}
    ]

@router.post("/story/generate")
async def generate_story(data: dict):
    # This would call the story_generator_service
    return {"status": "success", "message": "Story generation started", "job_id": "demo-job"}

@router.get("/scoreboard/data")
async def get_scoreboard():
    return {
        "teams": [
            {"name": "Team One", "score": 45},
            {"name": "Team Two", "score": 38}
        ]
    }
