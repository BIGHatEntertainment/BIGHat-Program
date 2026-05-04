"""
SharePoint Hybrid Sync — core engine.

A single `SyncService` that:

  - Enumerates files in a **remote** asset provider (anything implementing
    the small `SharePointService` surface: `list_folder_contents(path)` +
    `download_file_to_bytes(path)` + `upload_content(content, path)`).
  - Walks a **local** root on disk.
  - Computes the diff → plan → apply loop for `pull` (remote → local) and
    `push` (local → remote).
  - Persists sync state in a MontyDB `sync_state` collection so the UI
    can show "last pulled 3 minutes ago".

Design goals:

  1. Dev-friendly — we accept ANY asset service as `remote`, not just the
     real SharePoint one. In the dev container we point a second
     `LocalAssetService` at a sibling folder and exercise the full flow.
     In production the factory returns `SharePointService` and nothing
     else changes.
  2. Offline-first — pull/push never block on the network; the caller is
     expected to decide when to run them.
  3. Idempotent — re-running `pull` with no remote changes is a no-op.
  4. Traversal-safe — no path ever resolves outside `local_root`.

Sync key = the relative path of the file under the managed root
(e.g. `01_Trivia/Web App/00_Builder/01_Rounds/02_REG/History_1.pptx`).
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# Recursion limit to protect against accidental symlink loops or absurd
# remote trees. 8 is deep enough for the BIG Hat asset tree layout.
MAX_DEPTH = 8


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or datetime.now(timezone.utc)).isoformat()


@dataclass
class RemoteFile:
    """Normalised view of a file returned by the asset service."""
    path: str          # relative POSIX path under the sync root
    size: int
    modified: str      # ISO 8601; remote timestamp
    item_id: str       # opaque; equal to `path` for LocalAssetService


@dataclass
class LocalFile:
    path: str
    size: int
    modified: str


@dataclass
class SyncPlan:
    """Deterministic summary of actions required to reach convergence."""
    direction: str                                # 'pull' | 'push'
    to_add: List[str] = field(default_factory=list)       # missing on target
    to_update: List[str] = field(default_factory=list)    # size/mtime differs
    to_delete: List[str] = field(default_factory=list)    # extra on target
    unchanged: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction,
            "to_add": self.to_add,
            "to_update": self.to_update,
            "to_delete": self.to_delete,
            "unchanged_count": len(self.unchanged),
            "total_changes": len(self.to_add) + len(self.to_update) + len(self.to_delete),
        }


class SyncService:
    """Orchestrates pull/push between a remote asset service and a local root."""

    def __init__(
        self,
        remote_service,
        local_root: Path,
        *,
        sync_root_rel: str = "",
        db=None,
        delete_on_pull: bool = False,
        delete_on_push: bool = False,
    ):
        self.remote = remote_service
        self.local_root = Path(local_root).expanduser().resolve()
        self.sync_root_rel = sync_root_rel.strip("/")
        self.db = db
        self.delete_on_pull = delete_on_pull
        self.delete_on_push = delete_on_push
        self.local_root.mkdir(parents=True, exist_ok=True)

    # ----- Enumeration -----
    def _walk_remote(self, rel: str = "", depth: int = 0) -> List[RemoteFile]:
        if depth > MAX_DEPTH:
            logger.warning(f"[SYNC] remote walk aborted at {rel} (depth {depth})")
            return []
        # Scope the walk to sync_root_rel
        base = f"{self.sync_root_rel}/{rel}".strip("/") if rel else self.sync_root_rel
        out: List[RemoteFile] = []
        try:
            items = self.remote.list_folder_contents(base)
        except Exception as e:
            logger.error(f"[SYNC] remote list failed for {base}: {e}")
            return []

        for item in items:
            name = item.get("name", "")
            if not name:
                continue
            # Build the sync-key — relative path under the sync root, POSIX
            item_rel = f"{rel}/{name}".lstrip("/") if rel else name
            if item.get("folder"):
                out.extend(self._walk_remote(item_rel, depth + 1))
                continue
            size = int(item.get("size") or 0)
            modified = str(item.get("lastModifiedDateTime") or "")
            item_id = str(item.get("id") or item_rel)
            out.append(RemoteFile(path=item_rel, size=size, modified=modified, item_id=item_id))
        return out

    def _walk_local(self) -> List[LocalFile]:
        out: List[LocalFile] = []
        root = self.local_root
        if self.sync_root_rel:
            root = root / self.sync_root_rel
        if not root.exists() or not root.is_dir():
            return out
        for entry in root.rglob("*"):
            if not entry.is_file():
                continue
            rel = str(entry.relative_to(root)).replace("\\", "/")
            stat = entry.stat()
            out.append(LocalFile(
                path=rel,
                size=stat.st_size,
                modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            ))
        return out

    # ----- Planning -----
    def _plan(self, direction: str) -> SyncPlan:
        if direction not in ("pull", "push"):
            raise ValueError(f"unknown direction: {direction}")
        remote = {f.path: f for f in self._walk_remote()}
        local = {f.path: f for f in self._walk_local()}

        plan = SyncPlan(direction=direction)
        if direction == "pull":
            source, target = remote, local
            del_when = self.delete_on_pull
        else:
            source, target = local, remote
            del_when = self.delete_on_push

        for path, sf in source.items():
            tf = target.get(path)
            if tf is None:
                plan.to_add.append(path)
            elif sf.size != tf.size:
                # Size difference is the most reliable change signal; mtime
                # across SharePoint / local disk is often skewed by TZ.
                plan.to_update.append(path)
            else:
                plan.unchanged.append(path)
        # Deletions — items on target that source doesn't have
        if del_when:
            for path in target.keys():
                if path not in source:
                    plan.to_delete.append(path)
        return plan

    def plan(self, direction: str) -> SyncPlan:
        """Public dry-run: compute the plan but apply nothing."""
        return self._plan(direction)

    # ----- Path safety -----
    def _safe_local_path(self, rel: str) -> Path:
        base = self.local_root / self.sync_root_rel if self.sync_root_rel else self.local_root
        resolved = (base / rel).resolve()
        try:
            resolved.relative_to(base.resolve())
        except ValueError as e:
            raise ValueError(f"path escapes local root: {rel}") from e
        return resolved

    def _remote_path(self, rel: str) -> str:
        return f"{self.sync_root_rel}/{rel}".strip("/") if self.sync_root_rel else rel

    # ----- Apply: Pull -----
    def pull(self) -> Dict[str, Any]:
        plan = self._plan("pull")
        added: List[str] = []
        updated: List[str] = []
        deleted: List[str] = []
        errors: List[Dict[str, str]] = []

        for path in plan.to_add + plan.to_update:
            try:
                data = self.remote.download_file_to_bytes(self._remote_path(path))
                if not data:
                    errors.append({"path": path, "op": "download", "error": "empty"})
                    continue
                dst = self._safe_local_path(path)
                dst.parent.mkdir(parents=True, exist_ok=True)
                with open(dst, "wb") as fh:
                    fh.write(data)
                (added if path in plan.to_add else updated).append(path)
            except Exception as e:
                errors.append({"path": path, "op": "download", "error": str(e)})

        if self.delete_on_pull:
            for path in plan.to_delete:
                try:
                    dst = self._safe_local_path(path)
                    if dst.exists() and dst.is_file():
                        dst.unlink()
                        deleted.append(path)
                except Exception as e:
                    errors.append({"path": path, "op": "delete", "error": str(e)})

        result = {
            "direction": "pull",
            "added": added,
            "updated": updated,
            "deleted": deleted,
            "errors": errors,
            "unchanged_count": len(plan.unchanged),
            "finished_at": _iso(),
        }
        return result

    # ----- Apply: Push -----
    def push(self) -> Dict[str, Any]:
        plan = self._plan("push")
        added: List[str] = []
        updated: List[str] = []
        deleted: List[str] = []
        errors: List[Dict[str, str]] = []

        for path in plan.to_add + plan.to_update:
            try:
                src = self._safe_local_path(path)
                with open(src, "rb") as fh:
                    content = fh.read()
                ok = self.remote.upload_content(
                    content, self._remote_path(path),
                    content_type=_guess_mime(Path(path).suffix),
                )
                if ok:
                    (added if path in plan.to_add else updated).append(path)
                else:
                    errors.append({"path": path, "op": "upload", "error": "upload_failed"})
            except Exception as e:
                errors.append({"path": path, "op": "upload", "error": str(e)})

        # Remote-side deletes require a delete method; most asset services
        # don't expose one, so we only perform deletions when the remote
        # service actually has `delete_path` defined. This keeps the
        # default behaviour safe (never destructively alters cloud storage).
        if self.delete_on_push and hasattr(self.remote, "delete_path"):
            for path in plan.to_delete:
                try:
                    ok = self.remote.delete_path(self._remote_path(path))
                    if ok:
                        deleted.append(path)
                except Exception as e:
                    errors.append({"path": path, "op": "delete", "error": str(e)})

        return {
            "direction": "push",
            "added": added,
            "updated": updated,
            "deleted": deleted,
            "errors": errors,
            "unchanged_count": len(plan.unchanged),
            "finished_at": _iso(),
        }


def _guess_mime(suffix: str) -> str:
    return {
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".json": "application/json",
        ".mp3": "audio/mpeg",
        ".mp4": "video/mp4",
    }.get(suffix.lower(), "application/octet-stream")


# ----- State persistence -----
async def record_sync_run(db, kind: str, result: Dict[str, Any]) -> None:
    """Persist a sync run summary to MontyDB so `/api/native/sync/status`
    can report the last run.
    """
    if db is None:
        return
    doc = {
        "_id": f"last_{kind}",
        "kind": kind,
        "finished_at": result.get("finished_at"),
        "added": len(result.get("added") or []),
        "updated": len(result.get("updated") or []),
        "deleted": len(result.get("deleted") or []),
        "errors": len(result.get("errors") or []),
        "unchanged": result.get("unchanged_count", 0),
    }
    try:
        await db.sync_state.update_one(
            {"_id": doc["_id"]}, {"$set": doc}, upsert=True,
        )
    except Exception as e:
        logger.warning(f"[SYNC] Could not persist sync run {kind}: {e}")


async def get_sync_state(db) -> Dict[str, Any]:
    """Return last pull/push summaries for /status."""
    if db is None:
        return {"last_pull": None, "last_push": None}
    try:
        pull = await db.sync_state.find_one({"_id": "last_pull"}, {"_id": 0})
        push = await db.sync_state.find_one({"_id": "last_push"}, {"_id": 0})
        return {"last_pull": pull, "last_push": push}
    except Exception:
        return {"last_pull": None, "last_push": None}
