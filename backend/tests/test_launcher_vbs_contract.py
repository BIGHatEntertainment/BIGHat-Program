"""Locked launcher contract — `packaging/start_bighat.vbs` MUST open the
user's default browser, NOT a chromeless `--app=` window.

This is a hard rule from CHANGELOG v31.0.6 (and v31.0.14 reaffirms it
after a regression). The `--app=` mode caused two distinct customer-
blocking failures:

  v31.0.3   ERR_CONNECTION_REFUSED — race between backend startup and
            the chromeless window opening.
  v31.0.13  Blank deep-blue page on a customer machine — Edge AppData
            state quirk inside `--app=` mode, no visible JS console
            because DevTools is suppressed in app mode.

Any future change to the VBS that re-introduces `--app=`, pywebview,
chromiumExe candidate lookup, or msedge.exe path hardcoding fails this
test. Removing the test is also forbidden (it's tracked in git and a
PR removing it should bounce in review)."""
from __future__ import annotations

import re
from pathlib import Path

VBS = Path(__file__).resolve().parents[2] / "packaging" / "start_bighat.vbs"


def _vbs_code_only(text: str) -> str:
    """Strip VBS line comments (anything from `'` to end of line) so the test
    only inspects the executable code, not commentary explaining the rule."""
    out = []
    for line in text.splitlines():
        # First `'` outside any quoted string starts a comment.
        in_str = False
        cutoff = len(line)
        for i, ch in enumerate(line):
            if ch == '"':
                in_str = not in_str
            elif ch == "'" and not in_str:
                cutoff = i
                break
        out.append(line[:cutoff])
    return "\n".join(out)


def test_vbs_exists():
    assert VBS.is_file(), f"missing launcher VBS at {VBS}"


def test_vbs_does_not_use_app_mode():
    code = _vbs_code_only(VBS.read_text(encoding="utf-8-sig", errors="replace"))
    bad_patterns = [
        re.compile(r'--app=\s*"', re.IGNORECASE),
        re.compile(r'--app=\s*[a-z0-9]', re.IGNORECASE),
    ]
    for pat in bad_patterns:
        m = pat.search(code)
        assert not m, (
            f"start_bighat.vbs uses Edge/Chrome `--app=` chromeless mode. "
            f"This is forbidden — see CHANGELOG v31.0.6 NEVER-DO RULES. "
            f"Match: {m.group(0)!r}"
        )


def test_vbs_does_not_reference_msedge_or_pywebview():
    """`--app=` is reached via msedge.exe / chrome.exe lookup or via the
    `pywebview` Python wrapper. Both are forbidden by the same rule."""
    code = _vbs_code_only(
        VBS.read_text(encoding="utf-8-sig", errors="replace")
    ).lower()
    forbidden_tokens = ["msedge.exe", "pywebview", "chromiumexe"]
    found = [t for t in forbidden_tokens if t in code]
    assert not found, (
        f"start_bighat.vbs references chromeless-mode plumbing: {found}. "
        f"v31.0.6 NEVER-DO RULES require the launcher to open the user's "
        f"default browser via `WshShell.Run TARGET_URL, 1, False` only."
    )


def test_vbs_opens_default_browser():
    """Positive check: the active code path MUST contain the default-browser
    WshShell.Run call. Catches accidental deletion of the only working
    launcher line."""
    code = _vbs_code_only(VBS.read_text(encoding="utf-8-sig", errors="replace"))
    assert re.search(
        r"WshShell\.Run\s+TARGET_URL", code
    ), (
        "start_bighat.vbs is missing the canonical default-browser launch "
        "(`WshShell.Run TARGET_URL, 1, False`). The user explicitly approved "
        "this path in the v31.0.5 incident. See CHANGELOG."
    )
