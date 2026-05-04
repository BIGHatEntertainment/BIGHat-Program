"""
Local asset service — file-system mirror of `sharepoint_service.SharePointService`.

In native mode without a premium subscription we cannot reach SharePoint.
Instead, asset folders are read from the local data root configured by the
setup wizard (`paths.local_trivia` / `paths.assets` in system_config.json,
defaults to `BIGHAT_DATA_ROOT` env or `./data`).

This service mirrors the small subset of the SharePoint API actually used by
the trivia routes:

    list_folder_contents(folder_path) -> List[Dict like Graph driveItem]
    download_file(folder_path, local_dst) -> bool
    download_file_to_bytes(folder_path) -> bytes
    parse_sharepoint_path(path) -> (drive_id, item_id)  (always (None, None))
    download_file_by_item_id(...) -> mirrors local id back

`folder_path` semantics: a POSIX-style relative path that maps onto the local
asset root. Example: "01_Trivia/Web App/00_Builder/01_Hosts" lives at
`<asset_root>/01_Trivia/Web App/00_Builder/01_Hosts`.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import config_manager

logger = logging.getLogger(__name__)


def _asset_root() -> Path:
    paths = config_manager.config.get("paths", {})
    root = (
        os.environ.get("BIGHAT_ASSETS_DIR")
        or paths.get("assets")
        or paths.get("data_root")
        or "./data/assets"
    )
    p = Path(root).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


class LocalAssetService:
    """Local-filesystem implementation of the small SharePoint API."""

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root).expanduser().resolve() if root else _asset_root()
        self.root.mkdir(parents=True, exist_ok=True)
        logger.info(f"[NATIVE-MODE] LocalAssetService root={self.root}")

    # ----- Path helpers -----
    def _full(self, rel: str) -> Path:
        rel = (rel or "").lstrip("/")
        return (self.root / rel).resolve()

    # ----- API: list -----
    def list_folder_contents(self, folder_path: str) -> List[Dict]:
        """Return a list of pseudo-Graph driveItem dicts for the folder."""
        full = self._full(folder_path)
        if not full.exists() or not full.is_dir():
            logger.debug(f"LocalAssetService: missing folder {full}")
            return []

        items: List[Dict] = []
        for entry in sorted(full.iterdir(), key=lambda p: p.name.lower()):
            stat = entry.stat()
            rel = str(entry.relative_to(self.root)).replace("\\", "/")
            item = {
                "id": rel,  # local id == relative path, parseable & stable
                "name": entry.name,
                "size": stat.st_size,
                "parentReference": {"driveId": "local"},
                "lastModifiedDateTime": stat.st_mtime,
            }
            if entry.is_dir():
                item["folder"] = {"childCount": sum(1 for _ in entry.iterdir())}
            else:
                item["file"] = {"mimeType": _guess_mime(entry.suffix)}
            items.append(item)
        return items

    def list_folder_contents_by_sharing_url(self, sharing_url: str) -> List[Dict]:
        """In local mode there is no sharing URL — return empty."""
        logger.debug(f"LocalAssetService: ignoring SharePoint sharing url {sharing_url[:60]}…")
        return []

    # ----- API: download / read -----
    def download_file(self, file_path: str, local_path: str) -> bool:
        src = self._full(file_path)
        if not src.exists() or src.is_dir():
            logger.warning(f"LocalAssetService: cannot download missing file {src}")
            return False
        try:
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, local_path)
            return True
        except OSError as e:
            logger.error(f"LocalAssetService: copy failed {src} -> {local_path}: {e}")
            return False

    def download_file_to_bytes(self, file_path: str) -> bytes:
        src = self._full(file_path)
        if not src.exists() or src.is_dir():
            return b""
        try:
            with open(src, "rb") as fh:
                return fh.read()
        except OSError as e:
            logger.error(f"LocalAssetService: read failed {src}: {e}")
            return b""

    def get_file_url(self, file_path: str) -> str:
        return f"file://{self._full(file_path)}"

    # ----- API: SharePoint URI compatibility -----
    def parse_sharepoint_path(self, path: str) -> Tuple[Optional[str], Optional[str]]:
        """In local mode `sharepoint://drive/item` paths are not used; map any
        legacy id back to itself so the caller's `download_file_by_item_id`
        succeeds.
        """
        if path.startswith("sharepoint://"):
            rest = path[len("sharepoint://"):]
            parts = rest.split("/", 1)
            drive = parts[0] if parts else "local"
            item = parts[1] if len(parts) > 1 else ""
            return drive, item
        return "local", path

    def download_file_by_item_id(self, drive_id: str, item_id: str, local_path: str) -> bool:
        # `item_id` is our relative path
        return self.download_file(item_id, local_path)

    def download_file_by_sharing_url(self, sharing_url: str, local_path: str) -> bool:
        logger.debug("LocalAssetService: cannot download by sharing url in local mode")
        return False

    def download_file_from_sharing_folder(self, sharing_url: str, filename: str) -> bytes:
        return b""

    def upload_file(self, local_path: str, sharepoint_path: str) -> bool:
        dst = self._full(sharepoint_path)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, dst)
            return True
        except OSError as e:
            logger.error(f"LocalAssetService: upload failed {local_path} -> {dst}: {e}")
            return False

    def upload_content(
        self,
        content: bytes,
        sharepoint_path: str,
        content_type: str = "application/octet-stream",
    ) -> bool:
        dst = self._full(sharepoint_path)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            with open(dst, "wb") as fh:
                fh.write(content)
            return True
        except OSError as e:
            logger.error(f"LocalAssetService: upload_content failed {dst}: {e}")
            return False

    # Stub methods that some callers may invoke
    def get_access_token(self) -> str:
        return "local-mode"

    def get_site_id(self) -> str:
        return "local"

    def get_drive_id(self, site_id: str) -> str:
        return "local"

    def get_item_by_id(self, item_id: str) -> Dict:
        full = self._full(item_id)
        if not full.exists():
            return {}
        rel = str(full.relative_to(self.root)).replace("\\", "/")
        return {
            "id": rel,
            "name": full.name,
            "size": full.stat().st_size,
            "parentReference": {"driveId": "local"},
            "file" if full.is_file() else "folder": {},
        }

    def get_driveitem_info_from_sharing_url(self, sharing_url: str) -> Dict:
        return {}

    def encode_sharing_url(self, sharing_url: str) -> str:
        return sharing_url


def _guess_mime(suffix: str) -> str:
    s = suffix.lower()
    return {
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".png": "image/png",
        ".gif": "image/gif",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".mp3": "audio/mpeg",
        ".mp4": "video/mp4",
        ".json": "application/json",
    }.get(s, "application/octet-stream")
