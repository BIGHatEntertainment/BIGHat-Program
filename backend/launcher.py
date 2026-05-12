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
    try:
        (BACKEND_DIR / "data" / "logs").mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning(f"Could not pre-create data/logs/: {e}")

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
    """Load backend/.env if present, then force native mode."""
    _bootstrap_env_from_template()
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(BACKEND_DIR / ".env")
    except Exception as e:
        logger.warning(f"dotenv not loaded: {e}")
    os.environ.setdefault("BIGHAT_NATIVE_MODE", "1")
    # SECURITY: in installed copies the cloud licensing routes must NEVER load,
    # even if a stray BIGHAT_CLOUD_MODE leaks in via system env. Native mode
    # always wins on a desktop install.
    if os.environ.get("BIGHAT_NATIVE_MODE") == "1":
        os.environ["BIGHAT_CLOUD_MODE"] = "0"


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
    """Start uvicorn on a daemon thread so the main thread can drive the
    native window's event loop. Daemon = the server dies cleanly when the
    customer closes the window."""
    import uvicorn  # type: ignore

    def _run():
        try:
            uvicorn.run(
                "server:app",
                host=host,
                port=port,
                reload=reload,
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
    """Open the app inside a chromeless OS-native window via pywebview.

    Returns True if the window was created and event-looped to completion,
    False if the webview backend isn't available (caller should fall back
    to the system browser).
    """
    try:
        import webview  # type: ignore
    except ImportError as e:
        logger.warning(f"pywebview not installed ({e}); falling back to browser")
        return False

    try:
        webview.create_window(
            title="BIG Hat Entertainment",
            url=url,
            width=1440,
            height=900,
            min_size=(1024, 720),
            resizable=True,
            text_select=True,
            confirm_close=False,
            background_color="#0B1020",  # match host login page so no white flash on load
        )
    except TypeError:
        # Older pywebview builds use positional `title, url` and reject newer kwargs.
        webview.create_window("BIG Hat Entertainment", url)

    # On Windows EdgeChromium (Edge WebView2 runtime, preinstalled on Win 10
    # 21H1+ / Win 11) gives us a modern chromeless window. macOS auto-picks
    # WKWebView via Cocoa.
    gui = "edgechromium" if sys.platform == "win32" else ("cocoa" if sys.platform == "darwin" else None)

    # pywebview 3.4 .start() signature does NOT accept `icon` — that kwarg is
    # new in 4.x. We pin to 3.4 deliberately, so don't pass it. The taskbar
    # icon comes from the parent BIGHat.exe (or from python.exe in dev runs);
    # there's no separate window-icon API in 3.4.
    try:
        webview.start(gui=gui, debug=False)
        return True
    except TypeError as e:
        # Older 3.x sometimes rejects the gui kwarg name; retry positionally.
        logger.warning(f"webview.start(gui={gui!r}) rejected kwarg ({e}); retrying positional")
        try:
            webview.start(False, None, False, False, gui)  # debug, http_server, http_port, _exposed
            return True
        except Exception as e2:  # noqa: BLE001
            logger.exception(f"webview.start fallback also failed: {e2}")
            return False
    except Exception as e:  # noqa: BLE001 — backend may fail at runtime
        logger.exception(f"webview.start({gui!r}) failed at runtime: {e}; will fall back to browser")
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

        # 2. Wait for the port to come up before pointing the window at it
        #    (otherwise the customer sees a "can't reach" page for 1-2s).
        if not _wait_for_port(args.host, args.port, timeout=20.0):
            raise RuntimeError(
                f"Backend did not start listening on {args.host}:{args.port} within 20s. "
                f"See data/logs/launcher_crash.log for the uvicorn traceback."
            )

        # 3. Headless mode (e.g. when launched from the Windows installer Auto-start
        #    section) — never open a window.
        if args.no_browser:
            logger.info("--no-browser given; running headless. Press Ctrl+C to stop.")
            try:
                threading.Event().wait()  # block forever; uvicorn thread is daemon
            except KeyboardInterrupt:
                pass
            return 0

        # 4. Native chromeless window (default).
        if not args.browser_only:
            if _open_native_window(url):
                return 0
            logger.warning("Native window unavailable — falling back to browser.")

        # 5. Last-resort: open the system default browser. Reload-friendly,
        #    runs the server in the foreground until Ctrl+C.
        webbrowser.open_new(url)
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
