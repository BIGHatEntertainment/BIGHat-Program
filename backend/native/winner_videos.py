"""alpha.69: Winner videos for Bingo.
Two folders (the second one wins):
  1. bundled copies   backend/assets/winner_videos   (ship with the app, seeded into app data)
  2. app data folder  <data_root>/winner_videos      (the user's own; the Add button saves here)
A video belongs to a theme when its file name matches the theme name.
Names are compared with punctuation removed:  "(1980's).mp4" == "1980s" == "80s".
"(Generic).mp4" is used when a theme has no video of its own."""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

EXTS = (".mp4", ".webm", ".mov", ".m4v")
MIME = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}
BUNDLED = Path(__file__).resolve().parent.parent / "assets" / "winner_videos"


def user_dir() -> Path:
    env = os.environ.get("BIGHAT_WINNER_VIDEOS_DIR")
    if env:
        return Path(env)
    try:
        from native.config import DEFAULT_CONFIG_PATH
        return Path(DEFAULT_CONFIG_PATH).parent / "winner_videos"
    except Exception:
        return Path(__file__).with_name("winner_videos")


def bundled_dir() -> Path:
    env = os.environ.get("BIGHAT_WINNER_BUNDLED_DIR")
    return Path(env) if env else BUNDLED


def key(name: str) -> str:
    """'(1980's).mp4' -> '1980s'; 'Pop-Punk & Emo' -> 'poppunkandemo'."""
    base = Path(name).stem if Path(name).suffix.lower() in EXTS else name
    base = base.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", base)


def short_key(k: str) -> str:
    """1980s -> 80s, 1970s -> 70s, 2000s -> y2k (the old names)."""
    m = re.fullmatch(r"(19|20)(\d)0s", k)
    return (m.group(2) + "0s") if m else k


def seed() -> None:
    """Copy bundled videos into the user's folder (never overwrites the user's files)."""
    dest = user_dir()
    try:
        dest.mkdir(parents=True, exist_ok=True)
        b = bundled_dir()
        if b.is_dir():
            for f in b.iterdir():
                if f.suffix.lower() in EXTS and not (dest / f.name).exists():
                    shutil.copy2(f, dest / f.name)
    except OSError:
        pass


def _scan(folder: Path) -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    try:
        if folder.is_dir():
            for f in sorted(folder.iterdir()):
                if f.is_file() and f.suffix.lower() in EXTS and not f.name.startswith("."):
                    out[key(f.name)] = f
    except OSError:
        pass
    return out


def all_videos() -> Dict[str, Path]:
    """key -> file. Bundled first, then the user's folder overrides."""
    seed()
    v = _scan(bundled_dir())
    v.update(_scan(user_dir()))
    return v


def find(theme: str) -> Optional[Path]:
    """The winner video for a theme, or the generic one, or None."""
    vids = all_videos()
    k = key(theme or "")
    if k in vids:
        return vids[k]
    for name, p in vids.items():
        if name != "generic" and short_key(name) == short_key(k) and k:
            return p
    if k == "y2k" and "2000s" in vids:
        return vids["2000s"]
    if k == "2000s" and "y2k" in vids:
        return vids["y2k"]
    # a theme called "Emo" still finds "Pop-Punk and Emo" (whole-name match only, 3+ letters)
    if len(k) >= 3:
        for name, p in vids.items():
            if name != "generic" and (k in name or name in k):
                return p
    return vids.get("generic")


def listing() -> List[Dict[str, object]]:
    vids = all_videos()
    return [{"name": p.name, "theme": k, "size": p.stat().st_size, "bundled": not (user_dir() / p.name).exists()}
            for k, p in sorted(vids.items())]


def save_upload_file(filename: str, fileobj) -> Path:
    """Save from a file-like object, 1 MB at a time (no big video held in memory)."""
    name = Path(filename).name
    if Path(name).suffix.lower() not in EXTS:
        raise ValueError("bad_type")
    if not key(name):
        raise ValueError("bad_name")
    dest = user_dir()
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / name
    tmp = dest / (name + ".part")
    try:
        with open(tmp, "wb") as fh:
            shutil.copyfileobj(fileobj, fh, 1024 * 1024)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return target
