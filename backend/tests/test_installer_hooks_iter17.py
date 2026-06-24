"""
Iteration 17 — Static validation of NSIS installer-hooks fix.

Why: A customer hit
   "Error opening file for writing:
    C:\\Program Files\\BIG Hat Entertainment\\bighat-backend.exe"
during upgrade. The fix is a NSIS pre-install / pre-uninstall hook that
taskkills both running processes and waits ~800ms so Windows releases the
locked file handles before NSIS extracts the new binaries.

These tests are PURE STATIC checks — actual NSIS execution only runs at
install time on a Windows machine and cannot be exercised here.
"""

import json
import os
import re
from pathlib import Path

import pytest
import requests

REPO_ROOT = Path("/app")
SRC_TAURI = REPO_ROOT / "src-tauri"
NSH_PATH = SRC_TAURI / "installer-hooks.nsh"
TAURI_CONF_PATH = SRC_TAURI / "tauri.conf.json"
PRD_PATH = REPO_ROOT / "memory" / "PRD.md"

EXPECTED_SHELL_EXE = "BIG Hat Entertainment.exe"
EXPECTED_BACKEND_EXE = "bighat-backend.exe"


# ---------- installer-hooks.nsh: existence + non-empty ------------------


def test_nsh_file_exists_and_non_empty():
    assert NSH_PATH.exists(), f"{NSH_PATH} must exist"
    assert NSH_PATH.stat().st_size > 0, f"{NSH_PATH} must be non-empty"


@pytest.fixture(scope="module")
def nsh_text() -> str:
    return NSH_PATH.read_text(encoding="utf-8")


# ---------- installer-hooks.nsh: macro structure ------------------------


def test_nsh_defines_preinstall_macro(nsh_text):
    assert re.search(r"!macro\s+NSIS_HOOK_PREINSTALL\b", nsh_text), (
        "Must define `!macro NSIS_HOOK_PREINSTALL`"
    )


def test_nsh_defines_preuninstall_macro(nsh_text):
    assert re.search(r"!macro\s+NSIS_HOOK_PREUNINSTALL\b", nsh_text), (
        "Must define `!macro NSIS_HOOK_PREUNINSTALL`"
    )


def test_nsh_macros_end_with_macroend(nsh_text):
    macro_starts = len(re.findall(r"!macro\b", nsh_text))
    macro_ends = len(re.findall(r"!macroend\b", nsh_text))
    assert macro_starts == macro_ends, (
        f"Unbalanced macros: {macro_starts} !macro vs {macro_ends} !macroend"
    )
    assert macro_starts >= 2, "Expected at least 2 macros (PREINSTALL + PREUNINSTALL)"


def _slice_macro_body(text: str, macro_name: str) -> str:
    pattern = re.compile(
        rf"!macro\s+{re.escape(macro_name)}\b(.*?)!macroend",
        re.DOTALL,
    )
    m = pattern.search(text)
    assert m, f"Could not find !macro {macro_name} ... !macroend block"
    return m.group(1)


# ---------- installer-hooks.nsh: taskkill targets per macro -------------


@pytest.mark.parametrize(
    "macro_name", ["NSIS_HOOK_PREINSTALL", "NSIS_HOOK_PREUNINSTALL"]
)
def test_macro_kills_shell_exe(nsh_text, macro_name):
    body = _slice_macro_body(nsh_text, macro_name)
    pattern = re.compile(
        rf'taskkill\s+/F\s+/T\s+/IM\s+"{re.escape(EXPECTED_SHELL_EXE)}"'
    )
    assert pattern.search(body), (
        f"{macro_name} must taskkill {EXPECTED_SHELL_EXE!r} with /F /T /IM flags"
    )


@pytest.mark.parametrize(
    "macro_name", ["NSIS_HOOK_PREINSTALL", "NSIS_HOOK_PREUNINSTALL"]
)
def test_macro_kills_backend_exe(nsh_text, macro_name):
    body = _slice_macro_body(nsh_text, macro_name)
    pattern = re.compile(
        rf'taskkill\s+/F\s+/T\s+/IM\s+"{re.escape(EXPECTED_BACKEND_EXE)}"'
    )
    assert pattern.search(body), (
        f"{macro_name} must taskkill {EXPECTED_BACKEND_EXE!r} with /F /T /IM flags"
    )


@pytest.mark.parametrize(
    "macro_name", ["NSIS_HOOK_PREINSTALL", "NSIS_HOOK_PREUNINSTALL"]
)
def test_macro_uses_nsexec_for_each_taskkill(nsh_text, macro_name):
    body = _slice_macro_body(nsh_text, macro_name)
    nsexec_calls = re.findall(r"nsExec::Exec\s+'[^']*taskkill[^']*'", body)
    assert len(nsexec_calls) >= 2, (
        f"{macro_name} should invoke nsExec::Exec for both taskkills, "
        f"found {len(nsexec_calls)}"
    )


@pytest.mark.parametrize(
    "macro_name", ["NSIS_HOOK_PREINSTALL", "NSIS_HOOK_PREUNINSTALL"]
)
def test_macro_sleeps_after_taskkill(nsh_text, macro_name):
    """Windows needs a brief moment to release file handles after taskkill."""
    body = _slice_macro_body(nsh_text, macro_name)
    sleeps = re.findall(r"^\s*Sleep\s+(\d+)", body, flags=re.MULTILINE | re.IGNORECASE)
    assert sleeps, f"{macro_name} must include a Sleep after taskkills"
    assert any(int(ms) > 500 for ms in sleeps), (
        f"{macro_name} Sleep must be > 500ms (found: {sleeps})"
    )


# ---------- tauri.conf.json validity ------------------------------------


@pytest.fixture(scope="module")
def tauri_conf() -> dict:
    return json.loads(TAURI_CONF_PATH.read_text(encoding="utf-8"))


def test_tauri_conf_is_valid_json(tauri_conf):
    assert isinstance(tauri_conf, dict)


def test_tauri_conf_version_preserved(tauri_conf):
    assert tauri_conf.get("version") == "32.0.0-alpha.11", (
        f"version must remain '32.0.0-alpha.11', got {tauri_conf.get('version')!r}"
    )


def test_tauri_conf_product_name(tauri_conf):
    # productName drives the shell .exe filename ("BIG Hat Entertainment.exe")
    assert tauri_conf.get("productName") == "BIG Hat Entertainment"


def test_tauri_conf_external_bin_backend(tauri_conf):
    # externalBin name drives the sidecar .exe filename ("bighat-backend.exe")
    externals = tauri_conf.get("bundle", {}).get("externalBin", [])
    assert any(
        ext.endswith("bighat-backend") for ext in externals
    ), f"externalBin must reference 'binaries/bighat-backend', got {externals}"


def test_tauri_conf_installer_hooks_wired(tauri_conf):
    nsis = tauri_conf.get("bundle", {}).get("windows", {}).get("nsis", {})
    assert nsis.get("installerHooks") == "installer-hooks.nsh", (
        f"bundle.windows.nsis.installerHooks must be 'installer-hooks.nsh', "
        f"got {nsis.get('installerHooks')!r}"
    )


def test_tauri_conf_install_mode_permachine(tauri_conf):
    """perMachine ensures the hook runs as Administrator → taskkill has rights."""
    nsis = tauri_conf.get("bundle", {}).get("windows", {}).get("nsis", {})
    assert nsis.get("installMode") == "perMachine", (
        f"installMode must be 'perMachine', got {nsis.get('installMode')!r}"
    )


def test_installer_hooks_path_resolves_from_src_tauri(tauri_conf):
    nsis = tauri_conf.get("bundle", {}).get("windows", {}).get("nsis", {})
    rel = nsis.get("installerHooks")
    resolved = (SRC_TAURI / rel).resolve()
    assert resolved.exists(), (
        f"installerHooks path {rel!r} must resolve to an existing file "
        f"from src-tauri/, looked at {resolved}"
    )


# ---------- Cross-file: .nsh names match Tauri-produced .exe names ------


def test_nsh_exe_names_match_tauri_output(nsh_text, tauri_conf):
    """The taskkill targets must exactly match what Tauri produces on Windows."""
    product_name = tauri_conf["productName"]
    expected_shell = f"{product_name}.exe"  # "BIG Hat Entertainment.exe"

    externals = tauri_conf.get("bundle", {}).get("externalBin", [])
    backend_external = next(e for e in externals if e.endswith("bighat-backend"))
    expected_backend = f"{Path(backend_external).name}.exe"  # "bighat-backend.exe"

    assert f'"{expected_shell}"' in nsh_text, (
        f"installer-hooks.nsh must reference exactly {expected_shell!r} "
        "(matches tauri.conf.json productName + .exe)"
    )
    assert f'"{expected_backend}"' in nsh_text, (
        f"installer-hooks.nsh must reference exactly {expected_backend!r} "
        "(matches tauri.conf.json externalBin + .exe)"
    )


# ---------- PRD documentation -------------------------------------------


def test_prd_documents_installer_kill_invariant():
    text = PRD_PATH.read_text(encoding="utf-8")
    assert "INSTALLER MUST KILL RUNNING PROCESSES BEFORE OVERWRITE" in text, (
        "PRD.md must contain the new INSTALLER MUST KILL section"
    )
    # Both exe names should be called out in the doc too
    assert EXPECTED_SHELL_EXE in text
    assert EXPECTED_BACKEND_EXE in text


# ---------- Backend smoke (1 call, just to confirm nothing broke) -------


def test_backend_api_smoke():
    env_path = REPO_ROOT / "frontend" / ".env"
    base_url = None
    for line in env_path.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            base_url = line.split("=", 1)[1].strip().rstrip("/")
            break
    assert base_url, "REACT_APP_BACKEND_URL missing from /app/frontend/.env"

    resp = requests.get(f"{base_url}/api/", timeout=15)
    assert resp.status_code == 200, (
        f"GET {base_url}/api/ returned {resp.status_code}: {resp.text[:200]}"
    )
