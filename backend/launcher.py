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
import threading
import webbrowser
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_PORT = int(os.environ.get("BIGHAT_PORT", "8001"))


def _user_data_dir() -> Path:
    """Per-user writable data dir. Used in BOTH dev and PyInstaller-frozen
    modes so the embedded sqlite / .env / logs survive across upgrades and
    don't try to write into Program Files (which is read-only for
    non-elevated processes).

    Layout:
      • Windows: %LOCALAPPDATA%\\BIGHat\\data
      • macOS:   ~/Library/Application Support/BIGHat/data
      • Linux:   ~/.local/share/BIGHat/data  (dev container)
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "BIGHat" / "data"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "BIGHat" / "data"
    return Path.home() / ".local" / "share" / "BIGHat" / "data"


USER_DATA_DIR = _user_data_dir()
logger = logging.getLogger("bighat-launcher")


def _ensure_data_dirs() -> None:
    """Create the standard data directory tree if missing.

    The `data/logs/` directory is created unconditionally and FIRST so that
    `_write_crashlog()` always has somewhere to land — even if loading
    native.config blows up or any later step crashes. This was added after
    Phase 10.8 (pywebview migration) where a TypeError in the launcher
    caused a silent process exit with nothing on disk to diagnose.

    The remaining dirs (data_root / local_trivia / assets / generated) come
    from `native.config.config_manager` which owns the canonical defaults.
    """
    # 1. Crash-log destination — guaranteed-write before anything else.
    # In frozen mode BACKEND_DIR is read-only (_MEIxxxx temp dir), so we
    # fall back to USER_DATA_DIR. In dev BACKEND_DIR is writable and
    # mirrors the legacy layout, so we still create that one too.
    crash_dirs = [USER_DATA_DIR / "logs"]
    if not getattr(sys, "frozen", False):
        crash_dirs.append(BACKEND_DIR / "data" / "logs")
    for d in crash_dirs:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning(f"Could not pre-create {d}: {e}")

    # 2. Application data directories from system_config.json
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


def _quarantine_dev_seed_if_present() -> None:
    """v31.0.7 fix: builds before 31.0.7 shipped the dev `system_config.json`
    to customers (instance_id 75d181a8-…, master@bighat.local). On those
    installs the Setup Wizard never runs and login is unrecoverable. If we
    detect the well-known dev seed here, rename it to
    `system_config.dev-seed.json` so the ConfigManager falls back to
    defaults (setup_complete=False) and the wizard appears.

    Idempotent: once quarantined, the bad file is gone and this is a no-op.
    """
    # The config path matches `native.config.DEFAULT_CONFIG_PATH`.
    cfg_path = Path(
        os.environ.get(
            "BIGHAT_CONFIG_PATH",
            str(BACKEND_DIR / "native" / "system_config.json"),
        )
    )
    if not cfg_path.is_file():
        return
    try:
        import json as _json
        data = _json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[launcher] could not parse {cfg_path} (leaving alone): {e}")
        return
    # Signatures of the dev seed checked into the repo for builds <= 31.0.6.
    # We match on either the instance_id OR the master_admin_email to be
    # robust to either being copy-edited.
    DEV_INSTANCE_ID = "75d181a8-50f3-4032-90d4-7ecfd7cf44a7"
    is_dev_seed = (
        data.get("instance_id") == DEV_INSTANCE_ID
        or data.get("license_status", {}).get("master_admin_email") == "master@bighat.local"
    )
    if not is_dev_seed:
        return
    quarantine = cfg_path.with_name("system_config.dev-seed.json")
    try:
        cfg_path.rename(quarantine)
        logger.warning(
            "[launcher] quarantined dev-seed system_config.json -> %s. "
            "Setup Wizard will run on first request.",
            quarantine,
        )
    except OSError as e:
        logger.error(f"[launcher] could not quarantine dev seed at {cfg_path}: {e}")


def _bootstrap_env_from_template() -> Path | None:
    """First-run safety: if no `.env` exists but `.env.standalone` was
    shipped by the installer, copy it into place and replace the
    `__GENERATED_AT_FIRST_RUN__` placeholder with a fresh per-install
    `JWT_SECRET`. Returns the path written, or None if no template existed."""
    env_path = BACKEND_DIR / ".env"
    if env_path.is_file():
        return None
    template = BACKEND_DIR / ".env.standalone"
    if not template.is_file():
        return None
    import secrets as _secrets
    text = template.read_text(encoding="utf-8")
    text = text.replace("__GENERATED_AT_FIRST_RUN__", _secrets.token_hex(32))
    env_path.write_text(text, encoding="utf-8")
    try:
        env_path.chmod(0o600)
    except OSError:
        pass
    logger.info("[launcher] generated %s from .env.standalone (unique JWT_SECRET)", env_path)
    return env_path


def _load_env() -> None:
    """Load backend/.env if present, then force native mode + ensure every
    env var server.py reads has a sane writable default.

    In a PyInstaller-frozen sidecar `BACKEND_DIR` points at a read-only
    `_MEIxxxxxx` temp dir, so `.env` can't live there. We set defaults
    that point at the user-writable data dir instead — this is exactly
    what alpha.6 was missing (KeyError: 'MONGO_URL' on server.py:50).
    """
    _bootstrap_env_from_template()
    _quarantine_dev_seed_if_present()
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(BACKEND_DIR / ".env")
        # Also look in the per-user data dir — that's where the .env lives
        # for frozen installs (BACKEND_DIR is _MEI temp).
        load_dotenv(USER_DATA_DIR / ".env")
    except Exception as e:
        logger.warning(f"dotenv not loaded: {e}")
    os.environ.setdefault("BIGHAT_NATIVE_MODE", "1")
    # SECURITY: in installed copies the cloud licensing routes must NEVER load,
    # even if a stray BIGHAT_CLOUD_MODE leaks in via system env. Native mode
    # always wins on a desktop install.
    if os.environ.get("BIGHAT_NATIVE_MODE") == "1":
        os.environ["BIGHAT_CLOUD_MODE"] = "0"

    # ---- Defaults for env vars server.py reads via os.environ['...'] ----
    # These MUST be set before `from server import app` runs.
    #
    # server.py line ~51 calls `AsyncIOMotorClient(MONGO_URL)` BEFORE native
    # mode swaps the client for MontyDB — so MONGO_URL must be a syntactically
    # valid `mongodb://...` URI even though the connection is never made.
    # alpha.7 set it to a Windows path, which made pymongo's URI parser
    # interpret `C:\Users\...` as a host with a garbage port and crash:
    #   ValueError: Port must be an integer between 0 and 65535:
    #                '\\Users\\sella\\AppData\\Local\\BIGHat\\data\\montydb'
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    montydb_dir = USER_DATA_DIR / "montydb"
    montydb_dir.mkdir(parents=True, exist_ok=True)
    # Overwrite a malformed MONGO_URL (e.g. alpha.7 persisted a raw Windows
    # path instead of a URI, which crashed pymongo's parser).
    existing_mongo = os.environ.get("MONGO_URL", "")
    if not existing_mongo.startswith(("mongodb://", "mongodb+srv://")):
        if existing_mongo:
            logger.info("[launcher] overwriting non-URI MONGO_URL=%r with placeholder URI", existing_mongo)
        os.environ["MONGO_URL"] = "mongodb://127.0.0.1:27017"
    os.environ.setdefault("MONTYDB_DATA_DIR", str(montydb_dir))
    os.environ.setdefault("DB_NAME", "bighat")

    # Per-install random secrets — generated on first run, persisted to the
    # per-user .env so reinstalls / upgrades don't invalidate the master
    # admin password.
    persisted_env = USER_DATA_DIR / ".env"
    needs_persist = False
    if not os.environ.get("DEFAULT_HOST_PASSWORD"):
        import secrets as _s
        os.environ["DEFAULT_HOST_PASSWORD"] = _s.token_urlsafe(12)
        needs_persist = True
    if not os.environ.get("ADMIN_MASTER_PASSCODE"):
        import secrets as _s
        os.environ["ADMIN_MASTER_PASSCODE"] = _s.token_urlsafe(12)
        needs_persist = True
    if not os.environ.get("JWT_SECRET"):
        import secrets as _s
        os.environ["JWT_SECRET"] = _s.token_hex(32)
        needs_persist = True
    if needs_persist:
        try:
            existing = persisted_env.read_text(encoding="utf-8") if persisted_env.is_file() else ""
            keys_present = {line.split("=", 1)[0] for line in existing.splitlines() if "=" in line}
            new_lines = []
            for k in ("MONGO_URL", "MONTYDB_DATA_DIR", "DB_NAME",
                      "DEFAULT_HOST_PASSWORD", "ADMIN_MASTER_PASSCODE",
                      "JWT_SECRET"):
                if k not in keys_present:
                    new_lines.append(f"{k}={os.environ[k]}")
            if new_lines:
                with persisted_env.open("a", encoding="utf-8") as f:
                    if existing and not existing.endswith("\n"):
                        f.write("\n")
                    f.write("\n".join(new_lines) + "\n")
                try:
                    persisted_env.chmod(0o600)
                except OSError:
                    pass
                logger.info("[launcher] persisted generated secrets to %s", persisted_env)
        except OSError as e:
            logger.warning("[launcher] could not persist env to %s: %s", persisted_env, e)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BIG Hat Standalone launcher")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--no-browser", action="store_true", help="don't open any UI window")
    p.add_argument("--browser-only", action="store_true",
                   help="open the system default browser instead of the native window "
                        "(fallback if the embedded webview backend isn't available)")
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
    # Phase 9.1: surface installed version + pending update marker
    version_file = BACKEND_DIR / "VERSION.txt"
    version = (version_file.read_text(encoding="utf-8").strip()
               if version_file.is_file() else "unknown")
    print(f"[launcher] installed_ver = {version}")
    pending_marker = (
        Path(cfg.get("paths", {}).get("generated", BACKEND_DIR / "data" / "generated"))
        / "updates" / "pending_apply.json"
    )
    if pending_marker.is_file():
        try:
            import json as _json
            payload = _json.loads(pending_marker.read_text(encoding="utf-8"))
            print(
                f"[launcher] pending_apply= {payload.get('version')} "
                f"(scheduled {payload.get('scheduled_at')})"
            )
        except Exception:
            print(f"[launcher] pending_apply= present at {pending_marker}")
    else:
        print("[launcher] pending_apply= none")


def _open_browser_delayed(url: str, delay: float = 1.5) -> None:
    """[deprecated] Open the user's default browser to `url` on a background
    timer. Kept only for explicit `--browser-only` mode; the default launch
    path now uses a chromeless pywebview window via `_open_native_window()`.
    """
    def _open():
        try:
            webbrowser.open_new(url)
        except Exception as e:
            logger.warning(f"Could not open browser: {e}")

    threading.Timer(delay, _open).start()


def _show_native_error_dialog(title: str, message: str) -> None:
    """Show a blocking, native error dialog so the customer sees *something*
    when launch fails — instead of the embedded `pythonw.exe` exiting silently.

    Falls back to printing if the platform-specific dialog API isn't available.
    """
    try:
        if sys.platform == "win32":
            import ctypes  # stdlib, available in the embedded runtime
            MB_ICONERROR = 0x10
            MB_OK = 0x0
            ctypes.windll.user32.MessageBoxW(0, message, title, MB_ICONERROR | MB_OK)
            return
        if sys.platform == "darwin":
            import subprocess as _sp
            # AppleScript dialog — single line, no shell quoting headaches.
            script = (
                f'display dialog {message!r} '
                f'with title {title!r} buttons {{"OK"}} '
                'with icon stop default button "OK"'
            )
            _sp.run(["osascript", "-e", script], check=False, timeout=30)
            return
    except Exception as e:  # noqa: BLE001 — the dialog is best-effort
        logger.warning(f"Could not show native error dialog: {e}")
    # Last resort — at least put it on stdout/stderr.
    print(f"\n=== {title} ===\n{message}\n", file=sys.stderr)


def _write_crashlog(exc: BaseException) -> Path:
    """Write the current exception traceback to a stable log location and
    return that path so the dialog can point the customer at it."""
    import traceback
    # Prefer the user-writable data dir; fall back to BACKEND_DIR for dev.
    log_dir = USER_DATA_DIR / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_dir = BACKEND_DIR / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "launcher_crash.log"
    try:
        with log_path.open("a", encoding="utf-8") as f:
            from datetime import datetime, timezone
            f.write(f"\n===== {datetime.now(timezone.utc).isoformat()} =====\n")
            traceback.print_exc(file=f)
    except Exception:  # noqa: BLE001 — log write must never raise
        pass
    return log_path


def _wait_for_port(host: str, port: int, timeout: float = 30.0) -> bool:
    """Poll a TCP port until it accepts a connection. Returns True on success."""
    import socket
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def _start_uvicorn_in_thread(host: str, port: int, *, reload: bool) -> threading.Thread:
    """Start uvicorn on a daemon thread. Daemon = the server dies cleanly
    when the parent process exits."""
    import uvicorn  # type: ignore

    # IMPORTANT: PyInstaller-frozen sidecars don't have `server.py` sitting
    # on disk for uvicorn to import by string. Import the ASGI app object
    # ourselves and hand uvicorn the live object instead. This works in
    # both dev (python launcher.py) AND in the v32 Tauri PyInstaller
    # sidecar. See CHANGELOG v32.0.0-alpha.6.
    # reload= requires a string import target, so we only support reload
    # when not frozen.
    if reload and not getattr(sys, "frozen", False):
        target: object = "server:app"
    else:
        if reload:
            logger.warning("--reload ignored: not supported inside a PyInstaller-frozen sidecar")
        from server import app as target  # type: ignore[no-redef]

    def _run():
        try:
            uvicorn.run(
                target,  # type: ignore[arg-type]
                host=host,
                port=port,
                reload=reload and not getattr(sys, "frozen", False),
                log_level="info",
                log_config=None,
                access_log=False,
            )
        except SystemExit:
            pass
        except BaseException as exc:  # noqa: BLE001 — surface in crash log
            logger.exception("uvicorn thread failed: %s", exc)
            _write_crashlog(exc)

    t = threading.Thread(target=_run, name="uvicorn", daemon=True)
    t.start()
    return t


def _open_native_window(url: str) -> bool:
    """[DEPRECATED Phase 10.9] Browser opening is now done by
    `packaging/start_bighat.vbs` AFTER it confirms the port is listening.
    Kept as a stub so external callers don't break.
    """
    return False


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    # Make `import server` / `import native.*` work from anywhere.
    sys.path.insert(0, str(BACKEND_DIR))

    try:
        _load_env()
        _ensure_data_dirs()

        if args.check:
            _print_check(args.port)
            return 0

        url = f"http://{args.host}:{args.port}/"
        logger.info(f"Starting BIG Hat Entertainment — server at {url}")

        # 1. Boot uvicorn on a background thread.
        _start_uvicorn_in_thread(args.host, args.port, reload=args.reload)

        # 2. Wait for the port to come up.
        if not _wait_for_port(args.host, args.port, timeout=25.0):
            raise RuntimeError(
                f"Backend did not start listening on {args.host}:{args.port} within 25s. "
                f"See data/logs/launcher_crash.log for the uvicorn traceback."
            )

        # 3. Default mode for Windows/macOS installs: launched FROM `start_bighat.vbs`,
        #    which passes --no-browser and opens the user's default browser AFTER we
        #    confirm uvicorn is listening. We just keep the server alive here.
        #    --browser-only is the dev/diagnostic equivalent and opens the browser
        #    from Python directly.
        if not args.no_browser:
            webbrowser.open_new(url)
        else:
            logger.info("--no-browser given; VBS wrapper owns browser open. Running headless.")

        # 4. Block forever — uvicorn thread is daemon so it dies cleanly when
        #    Python exits (e.g. parent VBS terminates, or Ctrl+C in a dev console).
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return 0
    except SystemExit:
        raise
    except KeyboardInterrupt:
        return 130
    except BaseException as exc:  # noqa: BLE001 — top-level failure boundary
        log_path = _write_crashlog(exc)
        logger.exception("Launcher failed: %s", exc)
        _show_native_error_dialog(
            "BIG Hat Entertainment — failed to start",
            (
                "BIG Hat Entertainment couldn't start.\n\n"
                f"{type(exc).__name__}: {exc}\n\n"
                f"Full details have been written to:\n{log_path}\n\n"
                "Please send that file to support@bighat.live so we can help."
            ),
        )
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
