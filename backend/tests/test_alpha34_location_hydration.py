"""v32.0.0-alpha.34 regression suite.

Merchant report on alpha.33:
  * Location folder `monkey-pants-bar-grill/` exists on disk (survived
    from a prior install via OneDrive sync) but the fresh install's DB
    is empty, so the admin panel shows "No locations yet" and the Build
    Wizard's Choose-Location dropdown is empty.
  * The wizard's presentation payload does NOT carry branding + overlay
    images, so step 8-9 (build → launch) has no way to know which
    images belong to the selected location.
  * User requested comprehensive integrity checks so nothing "slips
    through or fails silently".

Alpha.34 lands three fixes:

  1) `_hydrate_from_disk()` — reconciles `db.locations` with
     `Files/Locations/*` folders. If a folder exists without a DB row,
     insert one with a derived name. If a DB row lacks its folder,
     mkdir. If `branding_images` / `overlay_images` records reference
     missing files, drop them; if orphan files exist without records,
     ingest them. Every reconciliation writes a WARNING log line
     tagged `[locations] hydrate:` so nothing fails silently.

  2) `GET /api/native/locations/health` — master-admin only integrity
     endpoint that runs the hydrator and returns the summary
     (db_rows, disk_folders, recovered_folders, created_folders,
     added_branding, removed_branding, added_overlays,
     removed_overlays, errors, ok, files_root).

  3) Wizard payload gains `nativeManifest` carrying the selected host's
     16:9 / 9:16 / avatar URLs and the location's full branding +
     overlay arrays with ready-to-render `/api/native/locations/...`
     URLs. Persisted on `TriviaPresentation.nativeManifest` so the
     presenter (step 9) has a launch-ready blob.

This test file locks in the shape + guard rails.
"""
from __future__ import annotations
import asyncio
from pathlib import Path


def test_locations_router_registers_health_endpoint():
    src = Path("/app/backend/native/locations_router.py").read_text()
    assert '@router.get("/health")' in src, (
        "GET /api/native/locations/health must be registered so master "
        "admins can run integrity checks from the app."
    )


def test_hydration_helper_exists_and_is_used_by_list():
    src = Path("/app/backend/native/locations_router.py").read_text()
    assert "async def _hydrate_from_disk" in src, "hydrator helper missing"
    # And list_locations() must call it before returning
    lstart = src.index("async def list_locations(")
    lend = src.index("@router.post(", lstart + 1) if "@router.post(" in src[lstart:] else lstart + 3000
    body = src[lstart:lend]
    assert "_hydrate_from_disk(" in body, (
        "list_locations() must invoke _hydrate_from_disk() so the "
        "admin panel auto-recovers OneDrive-restored folders."
    )


def test_trivia_locations_endpoint_also_hydrates():
    """The wizard hits /api/trivia/locations, potentially BEFORE the
    admin panel is opened. The endpoint must also trigger hydration so
    the dropdown never shows a stale empty state."""
    src = Path("/app/backend/routes/trivia.py").read_text()
    lstart = src.index("async def get_locations(")
    lend = src.index("@router.get(", lstart + 1)
    body = src[lstart:lend]
    assert "_hydrate_from_disk" in body, (
        "/api/trivia/locations must hydrate from disk to unblock the wizard "
        "on a fresh install whose DB is empty but has OneDrive folders."
    )


def test_native_manifest_field_on_import_request():
    src = Path("/app/backend/models.py").read_text()
    assert "nativeManifest" in src, (
        "TriviaImportRequest must carry a nativeManifest field so the "
        "wizard's payload survives to the persisted presentation."
    )


def test_wizard_payload_populates_native_manifest():
    src = Path("/app/frontend/src/components/trivia/TriviaBuilderWizard.jsx").read_text()
    assert "nativeManifest" in src, (
        "TriviaBuilderWizard must build a nativeManifest payload with "
        "host image URLs and location branding + overlay arrays."
    )
    # And it must include both branding + overlay URL fields
    assert "host_image_16x9" in src
    assert "host_image_9x16" in src
    assert "branding_images" in src
    assert "overlay_images" in src
    assert "/api/native/locations/" in src
    assert "/images/" in src
    assert "/overlays/" in src


def test_hydrate_from_disk_recovers_orphan_folder(tmp_path, monkeypatch):
    """Simulate a fresh alpha.34 install with an OneDrive-restored
    location folder but an empty DB: the hydrator should insert a
    DB row so the admin panel + wizard show the location."""
    import sys
    sys.path.insert(0, "/app/backend")
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))

    # Freshly reload so the module sees the tmp Files dir
    import importlib
    from native import locations_router as lr
    importlib.reload(lr)

    # Simulate OneDrive-synced folder from prior install
    slug = "old-bar-restored-from-onedrive"
    (tmp_path / "Files" / "Locations" / slug / "branding").mkdir(parents=True)
    (tmp_path / "Files" / "Locations" / slug / "overlays").mkdir(parents=True)
    orphan_file = tmp_path / "Files" / "Locations" / slug / "branding" / "seed.png"
    orphan_file.write_bytes(b"pretend-png-bytes")

    # Fresh in-memory MontyDB stand-in
    class _Coll:
        def __init__(self):
            self._docs = []
        def find(self, q, projection=None):
            docs = list(self._docs)
            class _C:
                def sort(self, *a, **k): return self
                async def to_list(self, n): return docs
            return _C()
        async def find_one(self, q, projection=None):
            for d in self._docs:
                if all(d.get(k) == v for k, v in q.items() if not k.startswith("$")):
                    return d
            return None
        async def insert_one(self, doc):
            self._docs.append(doc)
        async def update_one(self, q, update):
            for d in self._docs:
                if all(d.get(k) == v for k, v in q.items()):
                    d.update(update.get("$set", {}))

    class _DB:
        def __init__(self):
            self.locations = _Coll()

    lr._db = _DB()

    async def _run():
        summary = await lr._hydrate_from_disk()
        assert slug in summary["recovered_folders"], (
            f"orphan folder {slug!r} not recovered: {summary!r}"
        )
        assert summary["added_branding"].get(slug) == ["seed"], (
            f"orphan branding file not ingested: {summary!r}"
        )
        # Re-run — must be idempotent (no dupes).
        summary2 = await lr._hydrate_from_disk()
        assert slug not in summary2["recovered_folders"]

    asyncio.run(_run())
