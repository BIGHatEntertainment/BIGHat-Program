"""v32.0.0-alpha.33 regression suite — location pipeline unified.

Merchant report on alpha.32:
  * Location added in Admin Settings, but `Files/Locations/` folder
    stayed empty.
  * Location dropdown in Build Wizard was empty even though a location
    existed in the app.
  * No UI for uploading "round overlays" (semi-transparent overlays the
    presenter composites on top of each round).

Root cause: three disconnected pipelines. `db.locations` was the source
of truth for CRUD, uploads wrote to `<assets_root>/02_Locations/…`, and
`/api/trivia/locations` scanned yet a THIRD path
(`<assets_root>/01_Trivia/Web App/00_Builder/02_Locations/`) via the
legacy SharePoint client.

Alpha.33 unifies everything under `Files/Locations/<slug>/{branding,overlays}/`
and switches `/api/trivia/locations` to read from `db.locations` directly.

This test suite locks in:
  1. `_branding_dir(slug)` resolves under Files/Locations/.
  2. `_overlays_dir(slug)` exists and points at Files/Locations/<slug>/overlays/.
  3. Location documents carry an `overlay_images` field.
  4. The overlay upload / raw / delete / reorder endpoints exist and are
     mounted under `/api/native/locations/{id}/overlays[...]`.
  5. `/api/trivia/locations` no longer references SharePoint and
     returns rows sourced from db.locations with a non-empty `path`.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path


def test_branding_dir_lives_under_files_locations(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    sys.path.insert(0, "/app/backend")
    # Reload so `_files_locations_root` sees the override
    import importlib
    from native import locations_router as lr
    importlib.reload(lr)
    p = lr._branding_dir("phoenix-east")
    assert p.exists(), "_branding_dir should mkdir"
    assert p.name == "branding"
    assert p.parent.name == "phoenix-east"
    assert p.parent.parent.name == "Locations"
    assert p.parent.parent.parent.name == "Files"


def test_overlays_dir_lives_under_files_locations(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    sys.path.insert(0, "/app/backend")
    import importlib
    from native import locations_router as lr
    importlib.reload(lr)
    p = lr._overlays_dir("chicago")
    assert p.exists()
    assert p.name == "overlays"
    assert p.parent.name == "chicago"
    assert p.parent.parent.name == "Locations"


def test_alpha33_migration_marker_gets_written(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    sys.path.insert(0, "/app/backend")
    import importlib
    from native import locations_router as lr
    importlib.reload(lr)
    lr._branding_dir("marker-test")
    marker = tmp_path / "Files" / "Locations" / "marker-test" / ".alpha33-migrated"
    assert marker.is_file(), "alpha.33 migration marker not written"


def test_router_defines_overlay_endpoints():
    src = Path("/app/backend/native/locations_router.py").read_text()
    for pattern in (
        '@router.post("/{location_id}/overlays"',
        '@router.get("/{location_id}/overlays/{image_id}/raw"',
        '@router.delete("/{location_id}/overlays/{image_id}"',
        '@router.patch("/{location_id}/overlays/order"',
    ):
        assert pattern in src, f"missing overlay endpoint: {pattern!r}"


def test_trivia_locations_no_longer_uses_sharepoint():
    src = Path("/app/backend/routes/trivia.py").read_text()
    # Find get_locations function body
    start = src.index("async def get_locations(")
    end = src.index("@router.get(", start + 1)
    body = src[start:end]
    assert "SharePointService" not in body, (
        "get_locations() still references SharePointService"
    )
    assert "db.locations" in body or "_db.locations" in body or ".locations.find" in body
    assert "location:" in body, (
        "get_locations() must fall back to a `location:<id>` sentinel path "
        "so the Radix SelectItem in the wizard doesn't crash on value=''"
    )


def test_create_location_seeds_overlay_images_field():
    src = Path("/app/backend/native/locations_router.py").read_text()
    # Grab the create_location function body
    start = src.index("async def create_location(")
    end = src.index("@router.get(", start + 1)
    body = src[start:end]
    assert '"overlay_images": []' in body, (
        "create_location must seed overlay_images: [] on new locations "
        "so the frontend picker + presenter always find the field"
    )
