"""Regression guard for the v31.0.14 blank-window incident.

Root cause: undefined React reference (`<Cloud />` icon used without
being imported from `lucide-react`) compiled cleanly and shipped to
customers, where it threw `Uncaught ReferenceError: Cloud is not defined`
on React mount — producing a blank dark-blue window with no UI.

The release-build path (`yarn build` via craco) now treats `no-undef` and
`react/jsx-no-undef` as ERRORS (see `frontend/craco.config.js`). This
pytest is a fast offline check that runs ESLint directly so the
standalone-build pipeline (and CI) catches the regression in <10s instead
of after the full ~15s React build.

CHANGELOG: v31.0.15.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_frontend_has_no_undef_references():
    if not (FRONTEND / "node_modules").is_dir():
        pytest.skip("frontend/node_modules missing; run `yarn install` first")

    eslint = FRONTEND / "node_modules" / ".bin" / "eslint"
    if not eslint.is_file():
        pytest.skip(f"eslint binary not found at {eslint}")

    config_path = _write_flat_config()
    cmd = [
        str(eslint),
        "--config", str(config_path),
        "--quiet",
        "--format", "json",
        "src",
    ]
    proc = subprocess.run(
        cmd,
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        timeout=180,
    )

    if proc.returncode == 0:
        return

    try:
        results = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        pytest.fail(
            "eslint produced non-JSON output. "
            f"stderr:\n{proc.stderr}\nstdout (first 1500 chars):\n{(proc.stdout or '')[:1500]}"
        )

    offenders = []
    for f in results:
        for m in f.get("messages", []):
            if m.get("severity") == 2 and m.get("ruleId") in {
                "no-undef", "react/jsx-no-undef",
            }:
                offenders.append(
                    f"{f.get('filePath')}:{m.get('line')}:{m.get('column')}  "
                    f"[{m.get('ruleId')}]  {m.get('message')}"
                )
    if offenders:
        pytest.fail(
            "Frontend has undefined references — these crash the app at "
            "runtime with a blank window (see CHANGELOG v31.0.14/15):\n\n  "
            + "\n  ".join(offenders)
        )


def _write_flat_config() -> Path:
    """ESLint 9 flat config using the default Espree parser (which handles
    JSX when `ecmaFeatures.jsx` is on). Written into `frontend/` so Node
    can resolve `eslint-plugin-react` from `frontend/node_modules/`.
    Avoids needing @babel/eslint-parser or @typescript-eslint/parser
    (neither installed)."""
    out = FRONTEND / "node_modules" / ".cache" / "bighat-eslint.no-undef.config.mjs"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        """import reactPlugin from "eslint-plugin-react";
import globals from "globals";

export default [
  {
    files: ["src/**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      parserOptions: {
        ecmaVersion: 2022,
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.jest,
        URL: "readonly",
        URLSearchParams: "readonly",
        AbortController: "readonly",
        AudioContext: "readonly",
        IntersectionObserver: "readonly",
        ResizeObserver: "readonly",
        MutationObserver: "readonly",
        process: "readonly",
      },
    },
    plugins: { react: reactPlugin },
    rules: {
      "no-undef": "error",
      "react/jsx-no-undef": "error",
    },
    settings: { react: { version: "detect" } },
  },
];
""",
        encoding="utf-8",
    )
    return out
