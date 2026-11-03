"""Bingo "auto-advance songs" switch (v32.2.9), for BOTH Music Bingo and Traditional Bingo.

When ON, the host screen acts as the click on "Next song" / "Call next number" the moment the call timer reaches 0 (never "Start round").
This module only STORES the switch. It has its own file (bingo_auto_advance.json, next to bingo_settings.json) and its own routes, so no other save
(Setup, a new round, a new game, theme changes) can reset it by accident.

Fail-safe direction: any doubt means OFF. Default OFF. A missing, empty, damaged or hand-edited file reads as OFF (a damaged one is kept as .bad).
Only a real JSON `true` turns it on: the strings "true"/"1"/"on" or the number 1 are refused, so a stray value can never switch songs on by itself.
"""
import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("bighat-bingo-auto")
_lock = threading.Lock()


def _path() -> Path:
    """bingo_auto_advance.json, in the SAME folder as bingo_settings.json (the bingo library decides where that is)."""
    try:
        from native import bingo_library
        return bingo_library.settings_path().with_name("bingo_auto_advance.json")
    except Exception:                                              # noqa: BLE001
        return Path(__file__).with_name("bingo_auto_advance.json")


def _off() -> Dict[str, Any]:
    return {"enabled": False, "changed_at": None, "confirmed": False}


def get() -> Dict[str, Any]:
    """Current switch. Never raises; anything unclear is OFF."""
    p = _path()
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _off()
    except OSError:
        return _off()
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except ValueError:
        try:
            os.replace(p, p.with_suffix(".json.bad"))              # keep the evidence, start clean (OFF)
        except OSError:
            pass
        logger.warning("bingo auto-advance file was damaged; it is OFF")
        return _off()
    on = data.get("enabled") is True and data.get("confirmed") is True       # on only when explicitly confirmed by the host
    return {"enabled": on, "changed_at": data.get("changed_at"), "confirmed": data.get("confirmed") is True}


def set_enabled(enabled: Any, confirmed: Any = False) -> Dict[str, Any]:
    """Turn it on (needs host confirmation) or off. Returns the saved state. Raises ValueError for anything that is not a real boolean."""
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be true or false")
    if enabled and confirmed is not True:
        raise ValueError("the host must confirm before auto-advance is turned on")
    state = {"enabled": enabled, "confirmed": bool(enabled), "changed_at": datetime.now(timezone.utc).isoformat()}
    p = _path()
    with _lock:
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
    got = get()
    if got["enabled"] != enabled:                                   # read it back: never claim a state that did not stick
        raise RuntimeError("the setting could not be saved")
    return got
