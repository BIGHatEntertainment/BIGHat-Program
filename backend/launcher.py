"""
BIG Hat Standalone V31 — Native launcher.

Single entry point that boots the full offline app on one machine:
  1. Forces native mode + ensures the data directories exist.
  2. Starts uvicorn on 127.0.0.1:<BIGHAT_PORT> (default 8001).
  3. If a React `build/` bundle has been copied into `backend/static/`,
     the FastAPI process serves it from the same port so the user only
     needs one URL.
  4. Optionally opens the default browser to that URL.

Usage:
    python launcher.py               # run foreground
    python launcher.py --no-browser  # skip browser auto-open
    python launcher.py --port 18001  # override port

This file is intentionally dependency-light — no uvicorn CLI, no
setproctitle, etc. It should stay runnable with just `uvicorn` +
`python-dotenv` already pinned in `requirements.txt`.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import webbrowser
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_PORT = int(os.environ.get("BIGHAT_PORT", "8001"))

logger = logging.getLogger("bighat-launcher")


def _ensure_data_dirs() -> None:
    """Create the standard data directory tree if missing.

    Defers to `native.config.config_manager` which already owns the
    canonical defaults, then mkdir's whatever paths are configured.
    """
    try:
        from native.config import config_manager  # type: ignore
    except Exception as e:
        logger.warning(f"Could not import native.config (continuing): {e}")
        return
    paths = config_manager.config.get("paths", {}) or {}
    for key in ("data_root", "local_trivia", "assets", "generated"):
        p = paths.get(key)
        if p:
            try:
                Path(p).expanduser().mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.warning(f"Could not create {key}={p!r}: {e}")


def _load_env() -> None:
    """Load backend/.env if present, then force native mode."""
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(BACKEND_DIR / ".env")
    except Exception as e:
        logger.warning(f"dotenv not loaded: {e}")
    os.environ.setdefault("BIGHAT_NATIVE_MODE", "1")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BIG Hat Standalone launcher")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--no-browser", action="store_true", help="don't open the browser")
    p.add_argument("--reload", action="store_true", help="dev-only hot reload")
    p.add_argument("--check", action="store_true",
                   help="print config + exit (no server)")
    return p.parse_args(argv)


def _print_check(port: int) -> None:
    from native.config import config_manager  # type: ignore

    cfg = config_manager.public_view()
    print(f"[launcher] backend_dir   = {BACKEND_DIR}")
    print(f"[launcher] listen        = 127.0.0.1:{port}")
    print(f"[launcher] native_mode   = {os.environ.get('BIGHAT_NATIVE_MODE')}")
    print(f"[launcher] setup_complete= {cfg.get('setup_complete')}")
    print(f"[launcher] instance_id   = {cfg.get('instance_id')}")
    print(f"[launcher] paths         = {cfg.get('paths')}")
    static_dir = BACKEND_DIR / "static"
    has_static = static_dir.is_dir() and (static_dir / "index.html").exists()
    print(f"[launcher] static_bundle = {static_dir} (present={has_static})")


def _open_browser_delayed(url: str, delay: float = 1.5) -> None:
    """Open the user's default browser to `url` on a background timer."""
    import threading

    def _open():
        try:
            webbrowser.open_new(url)
        except Exception as e:
            logger.warning(f"Could not open browser: {e}")

    threading.Timer(delay, _open).start()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    # Make `import server` / `import native.*` work from anywhere.
    sys.path.insert(0, str(BACKEND_DIR))

    _load_env()
    _ensure_data_dirs()

    if args.check:
        _print_check(args.port)
        return 0

    # Import late — relies on env + sys.path above.
    import uvicorn  # type: ignore

    url = f"http://{args.host}:{args.port}/"
    if not args.no_browser:
        _open_browser_delayed(url)

    logger.info(f"Starting BIG Hat Standalone at {url}")
    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
