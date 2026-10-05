"""alpha.75: the Story Generator's own location images, stored ON THE PC (no SharePoint).

  Documents/BIG Hat Entertainment/Files/Story/
      Trivia/    <Location>.jpg            (location image)
                 <Location>_background.jpg (location background)
      Bingo/     <Location>.jpg
      Karaoke/   <Location>.jpg
      Hosts/     <Host name>.gif           (the host picture/GIF shown in every story)

A safety copy of every file is kept in <AppData>/backups/story/<kind>/ and restored if the Documents copy is lost.
Names are matched ignoring case, spaces, underscores and a leading "01_" style number.
"""
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from native import data_map

KINDS = ("Trivia", "Bingo", "Karaoke", "Hosts")   # Hosts: the host GIF/picture used by every story
VARIANTS = ("location", "background")          # background is only used by Trivia
EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
MAX_BYTES = 15 * 1024 * 1024
_BG_SUFFIX = "_background"


def root() -> Path:
    return data_map.docs_root() / "Story"


def backup_root() -> Path:
    return data_map.backups_dir() / "story"


def _kind(kind: str) -> str:
    k = (kind or "").strip().capitalize()
    if k not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    return k


def _variant(kind: str, variant: str) -> str:
    if kind == "Hosts":
        return "location"
    v = (variant or "location").strip().lower()
    if v not in VARIANTS:
        raise ValueError("variant must be 'location' or 'background'")
    if v == "background" and kind != "Trivia":
        raise ValueError("only the Trivia story uses a background image")
    return v


def clean_name(name: str) -> str:
    """Display name -> safe file stem. Keeps letters, numbers, spaces, - and ."""
    n = re.sub(r"[^A-Za-z0-9._ '&-]+", "", (name or "").strip()).strip(" .")
    return re.sub(r"\s+", " ", n)[:80]


def match_key(name: str) -> str:
    """Loose key so 'The Pub', 'the_pub' and '01_The_Pub' all match."""
    n = re.sub(r"^\d+[_\- ]+", "", (name or "").strip())
    return re.sub(r"[^a-z0-9]+", "", n.lower())


def ensure_folders() -> None:
    for k in KINDS:
        (root() / k).mkdir(parents=True, exist_ok=True)


def _stem_for(name: str, variant: str) -> str:
    return clean_name(name) + (_BG_SUFFIX if variant == "background" else "")


def _split(stem: str):
    if stem.lower().endswith(_BG_SUFFIX):
        return stem[: -len(_BG_SUFFIX)], "background"
    return stem, "location"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _looks_like_image(data: bytes) -> bool:
    return (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:6] in (b"GIF87a", b"GIF89a")
            or (data[:4] == b"RIFF" and data[8:12] == b"WEBP"))


def restore_missing() -> int:
    """Copy back any file that exists in the AppData safety copy but not in Documents."""
    n = 0
    for k in KINDS:
        src = backup_root() / k
        if not src.is_dir():
            continue
        for f in src.iterdir():
            if f.is_file() and f.suffix.lower() in EXTS and not (root() / k / f.name).exists():
                try:
                    (root() / k).mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, root() / k / f.name)
                    n += 1
                except OSError:
                    pass
    return n


def save(kind: str, name: str, data: bytes, variant: str = "location", ext: str = ".jpg") -> Dict[str, str]:
    kind = _kind(kind)
    variant = _variant(kind, variant)
    stem = _stem_for(name, variant)
    if not clean_name(name):
        raise ValueError("a location name is required")
    if not data or len(data) > MAX_BYTES:
        raise ValueError("image is empty or larger than 15 MB")
    if not _looks_like_image(data):
        raise ValueError("file is not a JPG, PNG, WEBP or GIF image")
    if ext.lower() == ".gif" and kind != "Hosts":
        raise ValueError("animated GIFs are only used for hosts")
    ext = ext.lower() if ext.lower() in EXTS else ".jpg"
    if data[:3] == b"GIF":
        ext = ".gif"
    # one image per (kind, name, variant): remove an older file with a different extension
    for old in list_files(kind):
        if match_key(old["name"]) == match_key(name) and old["variant"] == variant:
            delete_file(kind, old["filename"])
    fname = f"{stem}{ext}"
    _atomic_write(root() / kind / fname, data)
    try:
        _atomic_write(backup_root() / kind / fname, data)
    except OSError:
        pass
    return {"kind": kind, "filename": fname, "name": clean_name(name), "variant": variant}


def list_files(kind: str) -> List[Dict]:
    kind = _kind(kind)
    restore_missing()
    seen: Dict[str, Path] = {}
    for base in (root() / kind, backup_root() / kind):
        if not base.is_dir():
            continue
        for f in sorted(base.iterdir()):
            if f.is_file() and f.suffix.lower() in EXTS and not f.name.endswith(".part"):
                seen.setdefault(f.name, f)
    out = []
    for fname, f in sorted(seen.items()):
        name, variant = _split(f.stem)
        out.append({"kind": kind, "filename": fname, "name": name, "variant": variant, "size": f.stat().st_size})
    return out


def locations(kind: str) -> List[Dict]:
    """The dropdown list for a story builder: one entry per location that has a location image."""
    return [{"id": f["filename"], "name": f["name"], "filename": f["filename"], "has_background": False}
            for f in list_files(kind) if f["variant"] == "location"] if _kind(kind) != "Trivia" else _trivia_locations()


def _trivia_locations() -> List[Dict]:
    files = list_files("Trivia")
    bgs = {match_key(f["name"]) for f in files if f["variant"] == "background"}
    return [{"id": f["filename"], "name": f["name"], "filename": f["filename"], "has_background": match_key(f["name"]) in bgs}
            for f in files if f["variant"] == "location"]


def find(kind: str, name: str, variant: str = "location") -> Optional[Path]:
    """Path of the image for a location name, or None."""
    kind = _kind(kind)
    variant = _variant(kind, variant)
    key = match_key(name)
    if not key:
        return None
    restore_missing()
    for f in list_files(kind):
        if f["variant"] == variant and match_key(f["name"]) == key:
            p = root() / kind / f["filename"]
            if p.is_file():
                return p
    return None


def read_by_filename(kind: str, filename: str) -> Optional[bytes]:
    kind = _kind(kind)
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        return None
    restore_missing()
    for base in (root() / kind, backup_root() / kind):
        p = base / filename
        if p.is_file() and p.suffix.lower() in EXTS:
            try:
                return p.read_bytes()
            except OSError:
                continue
    return None


def delete_file(kind: str, filename: str) -> bool:
    kind = _kind(kind)
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        return False
    gone = False
    for base in (root() / kind, backup_root() / kind):
        p = base / filename
        if p.is_file():
            p.unlink()
            gone = True
    return gone


def hosts() -> List[Dict]:
    """Dropdown list of host pictures for the story builders."""
    return [{"id": f["filename"], "name": f["name"], "filename": f["filename"], "is_gif": f["filename"].lower().endswith(".gif")}
            for f in list_files("Hosts")]
