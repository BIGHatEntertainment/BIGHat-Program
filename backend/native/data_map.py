"""alpha.73: ONE place that says where the app keeps its data (so installs, updates, second PCs and backups all agree).

Two homes:
  APPDATA    %LOCALAPPDATA%\\BIGHat\\data              hidden, owned by the app: config, database, secure ledger, backups, logs
  DOCUMENTS  Documents\\BIG Hat Entertainment\\Files   visible to the merchant: things they browse, drop files into, or hand to staff

The rule: anything the merchant can SEE or EDIT lives in Documents; anything that is a SECRET lives in AppData only;
anything precious (locations, images, credentials) also has a second copy in AppData\\backups so it cannot be silently lost.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def appdata_root() -> Path:
    """The app's private data folder (the same one the launcher uses)."""
    env = os.environ.get("BIGHAT_DATA_ROOT") or os.environ.get("BIGHAT_DATA_DIR")
    if env:
        return Path(env)
    try:
        from native.config import DEFAULT_CONFIG_PATH
        return Path(DEFAULT_CONFIG_PATH).parent
    except Exception:
        return Path.home() / ".local" / "share" / "BIGHat" / "data"


def docs_root() -> Path:
    from native.files_router import _docs_root
    return _docs_root() / "Files"


def secure_dir() -> Path:
    return appdata_root() / "secure"


def backups_dir() -> Path:
    return appdata_root() / "backups"


def locations_backup_dir() -> Path:
    return backups_dir() / "locations"


def entries() -> List[Dict[str, Any]]:
    """Every place the app stores something, for the map file and the docs."""
    a, d = appdata_root(), docs_root()
    return [
        {"name": "Settings + users (hashed)", "home": "appdata", "path": str(a / "system_config.json"), "secret": True, "backed_up": True},
        {"name": "App database", "home": "appdata", "path": str(a), "secret": False, "backed_up": True},
        {"name": "Credential ledger (encrypted)", "home": "appdata", "path": str(secure_dir() / "credentials.ledger"), "secret": True, "backed_up": False},
        {"name": "Locations backup (copy of the images + settings)", "home": "appdata", "path": str(locations_backup_dir()), "secret": False, "backed_up": False},
        {"name": "Locations, branding + overlay images", "home": "documents", "path": str(d / "Locations"), "secret": False, "backed_up": True},
        {"name": "Trivia scores (saved nights)", "home": "documents", "path": str(d / "Trivia" / "Scores"), "secret": False, "backed_up": True},
        {"name": "Trivia scores safety copy", "home": "appdata", "path": str(backups_dir() / "scores"), "secret": False, "backed_up": True},
        {"name": "Trivia files", "home": "documents", "path": str(d / "Trivia"), "secret": False, "backed_up": True},
        {"name": "Bingo setup + songs", "home": "documents", "path": str(d / "Bingo"), "secret": False, "backed_up": True},
        {"name": "Karaoke (overlay, venue logos, songs)", "home": "documents", "path": str(d / "Karaoke"), "secret": False, "backed_up": True},
        {"name": "Winner videos", "home": "appdata", "path": str(a / "winner_videos"), "secret": False, "backed_up": False},
        {"name": "Logs", "home": "documents", "path": str(d / "Logs"), "secret": False, "backed_up": False},
    ]


def write_map() -> Path:
    """Write file_map.json into AppData so a reinstall / second PC / support call can see the layout."""
    root = appdata_root()
    root.mkdir(parents=True, exist_ok=True)
    p = root / "file_map.json"
    data = {"written_at": datetime.now(timezone.utc).isoformat(), "rule": __doc__.strip().splitlines()[3:9], "entries": entries()}
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    return p
