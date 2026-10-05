"""alpha.79: the Schedule saves what the Add Event form sends."""
import asyncio, os, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017"); os.environ.setdefault("DB_NAME", "test")   # server.py needs these to import
import server


def test_the_create_model_accepts_every_field_the_form_sends():
    form = {"title": "Halloween Bash", "event_type": "Special", "venue_id": "v1", "date": "2026-10-31T02:00:00.000Z",
            "duration_hours": 4, "pay_rate": 150, "notes": "costumes", "is_special_event": True}
    m = server.ScheduleEventCreate(**form)
    assert m.is_special_event is True and m.pay_rate == 150 and m.notes == "costumes" and m.duration_hours == 4
    assert set(form) <= set(server.ScheduleEventCreate.model_fields), "a field the form sends would be silently dropped"


def test_special_defaults_to_false_and_pay_zero_is_kept():
    m = server.ScheduleEventCreate(title="t", event_type="Trivia", venue_id="v", date="2026-10-12T01:00:00Z", pay_rate=0)
    assert m.is_special_event is False and m.pay_rate == 0


def test_create_and_update_models_cover_the_same_fields():
    c, u = set(server.ScheduleEventCreate.model_fields), set(server.ScheduleEventUpdate.model_fields)
    assert {"title", "event_type", "venue_id", "date", "duration_hours", "pay_rate", "notes", "is_special_event"} <= c
    assert {"title", "event_type", "venue_id", "date", "duration_hours", "pay_rate", "notes", "is_special_event"} <= u


class _FakeDb:
    class venues:
        @staticmethod
        async def find_one(q): return None
    class events:
        @staticmethod
        async def insert_one(d): raise AssertionError("nothing should be saved")


def test_a_blank_venue_gets_a_helpful_message_not_just_not_found(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(server, "db", _FakeDb)
    ev = server.ScheduleEventCreate(title="t", event_type="Trivia", venue_id="", date="2026-10-12T01:00:00Z")
    with pytest.raises(HTTPException) as e:
        asyncio.run(server.create_schedule_event(ev))
    assert e.value.status_code == 400 and "venue" in e.value.detail.lower() and "Venues" in e.value.detail


def test_an_unknown_venue_is_still_a_404(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(server, "db", _FakeDb)
    ev = server.ScheduleEventCreate(title="t", event_type="Trivia", venue_id="nope", date="2026-10-12T01:00:00Z")
    with pytest.raises(HTTPException) as e:
        asyncio.run(server.create_schedule_event(ev))
    assert e.value.status_code == 404
