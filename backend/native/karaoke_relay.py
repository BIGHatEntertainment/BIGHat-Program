"""alpha.82: connects a Karaoke night to the cloud relay so phones can request songs by QR.

How it works (plain terms):
  * When a night starts, we ask the relay for a night id -> that gives the QR link a phone CAN open.
  * While the night runs, every few seconds we ask the relay "any new requests?" and put them in the same
    list the host already uses (Accept / Reject). When the host answers, the answer goes back to the phone.
  * If the internet drops, nothing breaks: the QR keeps working for whoever already has the page, requests
    that came in meanwhile are picked up when the connection returns, and the host can always add songs by hand.
Every function here is safe to call: none of them raises."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from . import relay_client

logger = logging.getLogger("bighat-karaoke-relay")

POLL_SECONDS = 3.0          # while requests are coming in
IDLE_POLL_SECONDS = 10.0    # after a quiet minute (hundreds of venues share one server, so quiet nights should be cheap)
QUIET_AFTER_SECONDS = 60.0

_state: Dict[str, Any] = {"session": None, "url": None, "task": None, "answers": [], "online": None, "db": None, "last_activity": 0.0}


def status() -> Dict[str, Any]:
    return {"url": _state["url"], "online": _state["online"], "active": bool(_state["session"])}


def current_url() -> Optional[str]:
    return _state["url"]


async def start(db, venue: str) -> Dict[str, Any]:
    """Open (or reuse) the relay night and start the pull loop."""
    await stop(close_remote=False)
    _state["db"] = db
    _state["venue"] = venue
    res = await relay_client.open_night(venue or "Karaoke Night")
    if not res.get("ok"):
        _state["online"] = False
        logger.warning("[karaoke-relay] could not open a night: %s", res.get("error"))
        _ensure_loop()                         # keep trying: the internet may come back during the night
        return {"ok": False, "error": res.get("error"), "message": res.get("message")}
    _state.update(session=res["session"], url=res["url"], online=True, answers=[], last_activity=time.monotonic())
    _ensure_loop()
    return {"ok": True, "url": res["url"]}


def _ensure_loop() -> None:
    t = _state.get("task")
    if t is None or t.done():
        _state["task"] = asyncio.get_event_loop().create_task(_loop())


async def stop(close_remote: bool = True) -> None:
    t, sid = _state.get("task"), _state.get("session")
    _state.update(task=None, session=None, url=None, online=None, answers=[])
    if t and not t.done():
        t.cancel()
    if close_remote and sid:
        try:
            await relay_client.close_night(sid)
        except Exception:                      # noqa: BLE001
            pass


def note_answer(request_remote_id: str, status_value: str, position: int = 0) -> None:
    """Host accepted/rejected a phone request: remember to tell the phone on the next pull."""
    if request_remote_id and status_value in ("accepted", "rejected"):
        _state["last_activity"] = time.monotonic()
        _state["answers"].append({"id": request_remote_id, "status": status_value, "position": int(position or 0)})


async def _pull_once() -> int:
    sid, db = _state.get("session"), _state.get("db")
    if not sid or db is None:
        return 0
    answers, _state["answers"] = _state["answers"], []
    res = await relay_client.pull(sid, answers)
    if not res.get("ok"):
        _state["answers"] = answers + _state["answers"]        # try again next time
        _state["online"] = False
        if res.get("error", "").startswith("session_closed"):   # the relay forgot the night (expired): open a new one
            _state["session"] = None
        return 0
    _state["online"] = True
    n = 0
    for r in res.get("requests", []):
        if await db.karaoke_requests.find_one({"remote_id": r["id"]}):
            continue                                            # never twice
        await db.karaoke_requests.insert_one({
            "id": r["id"][:12], "remote_id": r["id"], "singer_name": r["singer_name"], "song_title": r["song_title"],
            "song_artist": r.get("song_artist", ""), "status": "pending", "position": 0,
            "created_at": r.get("created_at", ""), "source": "relay"})
        n += 1
    if n:
        _state["last_activity"] = time.monotonic()
    return n


def next_delay() -> float:
    """How long to wait before the next 'anything new?': quick while busy, relaxed after a quiet minute.
    A phone request waits at most IDLE_POLL_SECONDS the first time, then the loop is quick again."""
    quiet = time.monotonic() - float(_state.get("last_activity") or 0.0)
    return IDLE_POLL_SECONDS if quiet > QUIET_AFTER_SECONDS else POLL_SECONDS


async def _loop() -> None:
    reopen_in = 0.0
    while True:
        try:
            if not _state.get("session"):
                reopen_in -= next_delay()
                if reopen_in <= 0 and _state.get("db") is not None:
                    reopen_in = 20.0
                    res = await relay_client.open_night(_state.get("venue") or "Karaoke Night")
                    if res.get("ok"):
                        _state.update(session=res["session"], url=res["url"], online=True)
            else:
                await _pull_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:                  # noqa: BLE001
            logger.warning("[karaoke-relay] loop error: %s", e)
        await asyncio.sleep(next_delay())
