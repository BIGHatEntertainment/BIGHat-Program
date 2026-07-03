"""v32.0.0-alpha.36 — hardcoded round-type ↔ folder mapping.

Merchant report on alpha.35:
  Build Wizard stuck on Step 3 (Number of Rounds) with a red banner
  "Please wait for round files to load". The .bighat files were on
  disk under `Documents/BIG Hat Entertainment/Files/Trivia/{MC,REG,
  MISC,MYS,BIG}/` and the Files tool listed them correctly — but the
  wizard's `/api/trivia/round-files/<type>` endpoint returned [].

Root cause: `_list_local_round_files()` in routes/trivia.py was
looking for `.pptx` in the legacy SharePoint tree
`01_Trivia/Web App/00_Builder/01_Rounds/<01_MC|02_REG|…>/`. Never
touched the merchant's real `Files/Trivia/<TYPE>/` folder.

Fix (alpha.36):
  * NEW `_native_round_dir(round_type)` resolves the exact folder the
    merchant asked to be hardcoded:
       mc   -> Files/Trivia/MC/
       reg  -> Files/Trivia/REG/
       misc -> Files/Trivia/MISC/
       mys  -> Files/Trivia/MYS/
       big  -> Files/Trivia/BIG/
  * `_list_local_round_files()` scans that folder for `.bighat`
    files first, falls back to legacy `.pptx` for archived backups,
    and emits a fail-loud `[trivia] rounds type=X -> N file(s)` log
    line on every call.
"""
from __future__ import annotations
from pathlib import Path


SRC = Path("/app/backend/routes/trivia.py").read_text()


def test_native_round_dir_helper_exists():
    assert "def _native_round_dir(" in SRC, (
        "_native_round_dir() helper must resolve `Files/Trivia/<TYPE>/`"
    )
    assert '"Files"' in SRC and '"Trivia"' in SRC
    assert "round_type.upper()" in SRC, (
        "folder segment must be UPPERCASE (MC/REG/MISC/MYS/BIG)"
    )


def test_list_local_round_files_reads_bighat():
    assert '.bighat' in SRC.lower() or '".bighat"' in SRC, (
        "must read .bighat files from the native Trivia folder"
    )
    # And the function body must call _native_round_dir
    idx = SRC.index("def _list_local_round_files(")
    end = SRC.index("\n\n\n", idx)
    body = SRC[idx:end]
    assert "_native_round_dir" in body
    assert ".bighat" in body


def test_hardcoded_five_types_mapping():
    """Merchant asked for a strict 1-to-1 mapping. Verify none of the
    five folder names drift back to legacy '01_MC'/etc. under the new
    native path."""
    idx = SRC.index("def _native_round_dir(")
    end = SRC.index("\n\n\n", idx)
    body = SRC[idx:end]
    assert "01_MC" not in body
    assert "02_REG" not in body
    assert "03_MISC" not in body
    assert "04_MYS" not in body
    assert "05_BIG" not in body


def test_fail_loud_logging_on_every_fetch():
    assert '"[trivia] rounds type=' in SRC or "'[trivia] rounds type=" in SRC, (
        "every round-fetch must log the type + count so silent misses "
        "show up in supervisor logs"
    )


def test_reads_from_actual_folder_end_to_end(tmp_path, monkeypatch):
    """Live: drop a fake .bighat into MC/, call the helper, expect it
    in the result."""
    import sys, importlib
    sys.path.insert(0, "/app/backend")
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path))
    # Reload native.files_router so `_docs_root()` picks up the tmp dir
    from native import files_router as fr
    importlib.reload(fr)
    from routes import trivia as tr
    importlib.reload(tr)

    mc_dir = tmp_path / "Files" / "Trivia" / "MC"
    mc_dir.mkdir(parents=True)
    (mc_dir / "sample-round.bighat").write_text("fake")

    out = tr._list_local_round_files("mc")
    assert len(out) == 1, f"expected 1 round, got {out!r}"
    assert out[0]["type"] == "MC"
    assert out[0]["name"] == "sample-round"
    assert out[0]["path"].endswith("sample-round.bighat")
    # `path` must be non-empty so downstream Radix SelectItem doesn't
    # crash the wizard.
    assert out[0]["path"], "path must be non-empty"


def test_unknown_type_returns_empty_list():
    """Unknown round type must never 500 — just an empty list."""
    import sys, importlib
    sys.path.insert(0, "/app/backend")
    from routes import trivia as tr
    importlib.reload(tr)
    assert tr._list_local_round_files("nonsense") == []
    assert tr._list_local_round_files("") == []
