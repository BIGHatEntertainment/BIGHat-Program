"""alpha.73: trivia scores stored ON THE PC (no SharePoint needed).

Primary copy : Documents/BIG Hat Entertainment/Files/Trivia/Scores/<location>/<file>.json
Safety copy  : <AppData>/backups/scores/<location>/<file>.json
Every file is written to a temp name first, then renamed, so a crash never leaves half a file.
"""
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from native import data_map


def primary_root() -> Path:
    return data_map.docs_root() / "Trivia" / "Scores"


def backup_root() -> Path:
    return data_map.backups_dir() / "scores"


def extra_read_roots() -> List[Path]:
    """Folders we only READ score files from (never write or delete): Files/Scoreboard, where older builds and
    hand-copied score files live. The Scoreboard must find a score file wherever it sits under Files."""
    return [data_map.docs_root() / "Scoreboard"]


def _read_roots() -> List[Path]:
    return [primary_root(), backup_root(), *extra_read_roots()]


def _clean(text: str, fallback: str) -> str:
    t = re.sub(r"[^A-Za-z0-9._ -]+", "", (text or "").strip()).strip(" .")
    return re.sub(r"\s+", "_", t)[:60] or fallback


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def save(payload: Dict[str, Any]) -> Dict[str, str]:
    """Write one night's scores. Returns {folder, filename, path}. Never overwrites an earlier night."""
    folder = _clean(payload.get("location", ""), "Unknown_Location")
    date = _clean((payload.get("date") or "").replace("/", "-"), datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    base = f"{folder}_{date}"
    name, n = f"{base}.json", 1
    while (primary_root() / folder / name).exists():
        n += 1
        name = f"{base}_{n}.json"
    data = json.dumps(payload, indent=2).encode("utf-8")
    _atomic_write(primary_root() / folder / name, data)
    try:
        _atomic_write(backup_root() / folder / name, data)
    except OSError:
        pass                                   # the safety copy must never block the real save
    return {"folder": folder, "filename": name, "path": f"{folder}/{name}"}


def _file_id(folder: str, name: str) -> str:
    return f"{folder}/{name}"


def list_files() -> List[Dict[str, Any]]:
    """Same shape the dashboard already shows: [{location, folderId, fileCount, files:[{name,id,size,modified}]}].
    Looks in both places so a score file lost from Documents still shows up."""
    seen: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for root in _read_roots():
        if not root.is_dir():
            continue
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            for f in sorted(d.glob("*.json")):
                try:
                    st = f.stat()
                except OSError:
                    continue
                seen.setdefault(d.name, {}).setdefault(f.name, {
                    "name": f.name, "id": _file_id(d.name, f.name), "size": st.st_size,
                    "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                })
    return [{"location": loc, "folderId": loc, "fileCount": len(files), "files": sorted(files.values(), key=lambda x: x["name"])}
            for loc, files in sorted(seen.items())]


def _safe(file_id: str) -> Optional[tuple]:
    parts = (file_id or "").replace("\\", "/").split("/")
    if len(parts) != 2 or any(p in ("", ".", "..") for p in parts) or not parts[1].endswith(".json"):
        return None
    return parts[0], parts[1]


def read(file_id: str) -> Optional[Dict[str, Any]]:
    s = _safe(file_id)
    if not s:
        return None
    for root in _read_roots():
        f = root / s[0] / s[1]
        if f.is_file():
            try:
                return json.loads(f.read_text("utf-8"))
            except (OSError, ValueError):
                continue
    return None


def delete(file_id: str) -> bool:
    """Deliberate delete: removes both copies so it does not come back."""
    s = _safe(file_id)
    if not s:
        return False
    gone = False
    for root in (primary_root(), backup_root()):
        f = root / s[0] / s[1]
        if f.is_file():
            f.unlink()
            gone = True
    return gone


# ---------------------------------------------------------------- import a plain .json score file
class BadScoreFile(ValueError):
    """The file is not a score night. The message is safe to show the user."""


def validate_score_json(raw: bytes) -> Dict[str, Any]:
    """Parse and check an imported score file. A night needs a list of teams, each with a name."""
    if len(raw) > 5 * 1024 * 1024:
        raise BadScoreFile("That file is too large to be a score file.")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise BadScoreFile("That file is not valid JSON, so it cannot be read as a score file.")
    if not isinstance(data, dict) or not isinstance(data.get("teams"), list) or not data["teams"]:
        raise BadScoreFile("That JSON file does not look like a saved trivia night (it has no list of teams).")
    for t in data["teams"]:
        if not isinstance(t, dict) or not str(t.get("name", "")).strip():
            raise BadScoreFile("Every team in a score file needs a name.")
    return data


def import_json(raw: bytes) -> Dict[str, str]:
    """Validate a score file and save it exactly like a Trivia 'Save & Exit' night (never overwrites an earlier night)."""
    data = validate_score_json(raw)
    data.setdefault("location", str(data.get("locationName") or "Imported"))
    data.setdefault("date", str(data.get("presentationDate") or datetime.now(timezone.utc).strftime("%Y-%m-%d")))
    return save(data)
