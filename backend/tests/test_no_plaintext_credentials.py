"""Regression guard: refuse to ship any plaintext password, dev license key,
or known leaked-secret token in tracked source under backend/, frontend/,
or scripts/.

Triggered by v31.0.10 incident (the public repo had `password: "B1GHat"`
hardcoded in `server.py:441` and a bcrypt-hashed dev seed `system_config.json`
checked in to git).

If this test fails, DON'T just delete the offending line — rotate the
password too, because the repo is public and the value is already
compromised."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Patterns that are *never* OK to ship in tracked source.
FORBIDDEN = [
    # Specific historically-leaked passwords (rotate if you ever match here).
    re.compile(r'\bB1GHat\b'),
    re.compile(r'\bBigHat2024!\b'),
    # bcrypt hash signature with a salt rounds <= 14 (the dev seed used $2b$12$…).
    # Looking for the leak-pattern, not the prefix on its own, since we DO want
    # bcrypt validation code to live in source.
    re.compile(r'\$2[aby]\$\d{2}\$[./A-Za-z0-9]{50,}'),
    # GitHub PATs / OpenAI keys / Resend keys / common leaked-secret formats.
    re.compile(r'\bghp_[A-Za-z0-9]{36}\b'),
    re.compile(r'\bsk-[A-Za-z0-9]{20,}\b'),
    re.compile(r'\bre_[A-Za-z0-9]{15,}\b'),
]

# Files / dirs we deliberately allow to keep credential-looking content:
#   - This test file itself (we name the leaked values to detect them).
#   - The CHANGELOG (it documents the incident).
#   - Vendored reference snapshot under _reference/ (historical, untouched).
#   - Compiled .so files (binary).
#   - Migrations / fixtures that ship example data.
ALLOWED_PATHS = (
    "backend/tests/test_no_plaintext_credentials.py",
    "memory/CHANGELOG.md",
    "_reference/",
    ".so",
    ".lock",
    "package-lock.json",
    "yarn.lock",
    # Historical test reports may quote the leaked value verbatim. They're
    # immutable artifacts of prior runs.
    "test_reports/",
)


def _tracked_files() -> list[Path]:
    """Run `git ls-files` from the repo root."""
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return [ROOT / p for p in out.splitlines() if p.strip()]


def test_no_plaintext_credentials_in_tracked_source():
    failures: list[str] = []
    for f in _tracked_files():
        rel = f.relative_to(ROOT).as_posix()
        if any(a in rel for a in ALLOWED_PATHS):
            continue
        if not f.is_file():
            continue
        # Skip large / binary files
        try:
            content = f.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        for pat in FORBIDDEN:
            for m in pat.finditer(content):
                # Compute the line number for a useful error.
                line = content.count("\n", 0, m.start()) + 1
                failures.append(f"{rel}:{line}: matches {pat.pattern!r}: {m.group(0)[:40]}…")
    assert not failures, (
        "Plaintext credentials / leaked-secret tokens found in tracked source:\n"
        + "\n".join(f"  - {x}" for x in failures)
        + "\n\nRemediation:\n"
        + "  1. Remove the offending value from source.\n"
        + "  2. ROTATE the credential — the repo is public so it's compromised.\n"
        + "  3. If this is intentional (test/demo data only), add the path to\n"
        + "     ALLOWED_PATHS in this file."
    )


def test_system_config_json_is_not_tracked():
    """v31.0.10 incident: dev seed system_config.json was checked into the
    public repo, exposing the bcrypt hash + license key. It must stay
    gitignored."""
    out = subprocess.run(
        ["git", "ls-files", "backend/native/system_config.json"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert out == "", (
        "backend/native/system_config.json is tracked in git. It contains "
        "per-install credentials (master admin bcrypt, license key, HWID) "
        "and must be gitignored. Run: `git rm --cached backend/native/system_config.json`"
    )


def test_compiled_frontend_bundle_is_not_tracked():
    """The pre-compiled bundle (backend/static/static/js/main.*.js) is a build
    artifact reproducible from scripts/build_standalone.py and must not be
    tracked. It also accidentally bakes REACT_APP_BACKEND_URL into the
    bundle — see v31.0.10 incident."""
    out = subprocess.run(
        ["git", "ls-files", "backend/static/static/"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert out == "", (
        "Compiled frontend bundle under backend/static/static/ is tracked in "
        "git. This is a build artifact. Run: "
        "`git rm --cached -r backend/static/static/`."
    )
