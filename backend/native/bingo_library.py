"""
alpha.67: Bingo library = ONE main folder chosen in Bingo Setup.

    <main folder>/
        <Theme A>/          e.g. "1980s", "Emo", "Pop Punk"
            songs.xlsx|csv  number, song title, artist   (any file name)
            01_Song.mp4     videos, matched by the number the file name starts with
            02_Other.mp4
        <Theme B>/ ...

No SharePoint. Settings live in bingo_settings.json next to the app config.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

VIDEO_EXTS = (".mp4", ".webm", ".mov", ".m4v", ".mkv", ".avi")
LIST_EXTS = (".xlsx", ".xls", ".csv")
MIME = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm",
        ".mov": "video/quicktime", ".mkv": "video/x-matroska", ".avi": "video/x-msvideo"}


# ---------------------------------------------------------------- settings
def settings_path() -> Path:
    env = os.environ.get("BIGHAT_BINGO_SETTINGS")
    if env:
        return Path(env)
    try:
        from native.config import DEFAULT_CONFIG_PATH
        return Path(DEFAULT_CONFIG_PATH).with_name("bingo_settings.json")
    except Exception:
        return Path(__file__).with_name("bingo_settings.json")


def _default() -> Dict[str, Any]:
    return {"main_folder": "", "themes": {}}   # themes: { "<folder name>": {"enabled": bool} }


def load_settings() -> Dict[str, Any]:
    p = settings_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        out = _default()
        out["main_folder"] = str(data.get("main_folder") or "")
        out["themes"] = {str(k): {"enabled": bool((v or {}).get("enabled", True))}
                         for k, v in (data.get("themes") or {}).items()}
        return out
    except (OSError, ValueError):
        return _default()


def save_settings(main_folder: str, themes: Dict[str, Any]) -> Dict[str, Any]:
    data = {"main_folder": str(main_folder or "").strip(),
            "themes": {str(k): {"enabled": bool((v or {}).get("enabled", True)) if isinstance(v, dict) else bool(v)}
                       for k, v in (themes or {}).items()}}
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return load_settings()


# ---------------------------------------------------------------- scanning
def _song_list_file(folder: Path) -> Optional[Path]:
    """The one song list in a theme folder (first match, xlsx preferred over csv)."""
    files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in LIST_EXTS
             and not f.name.startswith(("~$", "."))]
    files.sort(key=lambda f: (LIST_EXTS.index(f.suffix.lower()), f.name.lower()))
    return files[0] if files else None


def video_number(name: str) -> Optional[int]:
    m = re.match(r"^\s*(\d+)", name)
    return int(m.group(1)) if m else None


def video_map(folder: Path) -> Dict[int, str]:
    """{song number: file name} for every video whose name starts with a number."""
    out: Dict[int, str] = {}
    for f in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTS:
            n = video_number(f.name)
            if n is not None and n not in out:
                out[n] = f.name
    return out


def scan(main_folder: str) -> Dict[str, Any]:
    """Look inside the main folder. One entry per sub folder (theme)."""
    root = Path(main_folder) if main_folder else None
    if not root or not str(main_folder).strip():
        return {"ok": False, "error": "no_folder", "themes": []}
    if not root.is_dir():
        return {"ok": False, "error": "folder_not_found", "themes": []}
    settings = load_settings()
    themes: List[Dict[str, Any]] = []
    try:
        subs = sorted([d for d in root.iterdir() if d.is_dir() and not d.name.startswith((".", "_"))],
                      key=lambda d: d.name.lower())
    except OSError:
        return {"ok": False, "error": "folder_not_readable", "themes": []}
    for d in subs:
        try:
            lst = _song_list_file(d)
            vids = video_map(d)
        except OSError:
            continue
        problems = []
        if not lst:
            problems.append("no song list (.xlsx or .csv)")
        if not vids:
            problems.append("no videos named like 01_Song.mp4")
        enabled = settings["themes"].get(d.name, {}).get("enabled", True)
        themes.append({"id": d.name, "name": d.name, "song_list": lst.name if lst else None,
                       "videos": len(vids), "ready": not problems, "problems": problems,
                       "enabled": bool(enabled)})
    return {"ok": True, "error": None, "themes": themes}


def available_themes() -> List[Dict[str, Any]]:
    """Themes the Music Bingo step may show: ready AND switched on."""
    s = load_settings()
    res = scan(s["main_folder"])
    return [t for t in res["themes"] if t["ready"] and t["enabled"]]


def theme_folder(theme_id: str) -> Optional[Path]:
    """Safe path to a theme folder (no escaping the main folder)."""
    s = load_settings()
    if not s["main_folder"] or not theme_id or theme_id in (".", "..") or re.search(r"[\\/]", theme_id):
        return None
    root = Path(s["main_folder"]).resolve()
    p = (root / theme_id).resolve()
    if p.parent != root or not p.is_dir():
        return None
    return p


# ---------------------------------------------------------------- song lists
def _clean(v: Any) -> str:
    s = "" if v is None else str(v).strip()
    return "" if s.lower() in ("nan", "none") else s


def _to_int(v: Any) -> Optional[int]:
    try:
        f = float(str(v).strip())
        return int(f) if f == int(f) else None
    except (ValueError, TypeError):
        return None


def _rows_from_file(path: Path) -> List[List[Any]]:
    if path.suffix.lower() == ".csv":
        raw = path.read_bytes()
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        try:
            dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        return [row for row in csv.reader(io.StringIO(text), dialect)]
    import pandas as pd
    df = pd.read_excel(path, header=None, engine="openpyxl" if path.suffix.lower() == ".xlsx" else None)
    return df.where(df.notna(), None).values.tolist()


def parse_song_list(path: Path) -> List[Dict[str, Any]]:
    """[{number, title, artist}] from a csv/xlsx. Works with or without a header row.
    Columns are found by header words (number/#, song/title, artist) and otherwise by
    position: number, title, artist."""
    rows = [r for r in _rows_from_file(path) if any(_clean(c) for c in r)]
    if not rows:
        return []
    ci = {"number": 0, "title": 1, "artist": 2}
    first = [_clean(c).lower() for c in rows[0]]
    if _to_int(rows[0][0] if rows[0] else None) is None and any(first):   # first row is a header
        for i, h in enumerate(first):
            if re.fullmatch(r"#|no\.?|num(ber)?|song\s*(#|no\.?|num(ber)?)|bingo\s*(#|number)", h):
                ci["number"] = i
            elif re.search(r"title|song|track|name", h) and "number" not in h and not re.fullmatch(r"song\s*(#|no\.?|num(ber)?)", h):
                ci["title"] = i
            elif "artist" in h or "band" in h or "performer" in h:
                ci["artist"] = i
        rows = rows[1:]
    out: List[Dict[str, Any]] = []
    seen = set()
    for r in rows:
        get = lambda k: r[ci[k]] if ci[k] < len(r) else None
        n = _to_int(get("number"))
        title = _clean(get("title"))
        if n is None or not title or n in seen:
            continue
        seen.add(n)
        out.append({"number": n, "title": title, "artist": _clean(get("artist"))})
    out.sort(key=lambda s: s["number"])
    return out


def theme_songs(theme_id: str) -> Optional[Dict[str, Any]]:
    """Songs for a theme, each flagged with whether its video file exists."""
    folder = theme_folder(theme_id)
    if not folder:
        return None
    lst = _song_list_file(folder)
    if not lst:
        return {"theme": theme_id, "songs": [], "error": "no_song_list"}
    songs = parse_song_list(lst)
    vids = video_map(folder)
    for s in songs:
        s["has_video"] = s["number"] in vids
    return {"theme": theme_id, "song_list": lst.name, "songs": songs,
            "missing_videos": [s["number"] for s in songs if not s["has_video"]], "error": None}


def video_path(theme_id: str, number: int) -> Optional[Path]:
    folder = theme_folder(theme_id)
    if not folder:
        return None
    name = video_map(folder).get(int(number))
    return (folder / name) if name else None
