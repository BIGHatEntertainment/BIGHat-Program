#!/usr/bin/env python3
"""Release gate: run the FROZEN backend (the exact binary that ships) on a throw-away data folder and fail if it is not whole.

Why: in v32.1.8 the Scoreboard router crashed while loading inside the installed app (a folder it created next to its own file, which is
read-only inside the PyInstaller bundle). The app started fine, so nothing noticed, and every Scoreboard button answered not_found.
This runs after the sidecar is built and BEFORE the installers are made, so a broken bundle never reaches a release.

Usage: python scripts/smoke_frozen_backend.py <path to the built bighat-backend binary>
Checks: (1) /health, (2) /api/diagnostics/routers lists NO failed router, (3) the Scoreboard answers (GET /scores/local and the
older POST /scores/import must NOT be not_found), (4) Save & Exit then Fetch round-trips one score file.
"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error


def free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def call(port, method, path, body=None, timeout=20):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main() -> int:
    exe = sys.argv[1]
    home = tempfile.mkdtemp(prefix="bighat_smoke_")
    port = free_port()
    env = dict(os.environ, HOME=home, USERPROFILE=home, BIGHAT_PORT=str(port), BIGHAT_DATA_ROOT=os.path.join(home, "appdata"),
               BIGHAT_CONFIG_PATH=os.path.join(home, "appdata", "system_config.json"), LOCALAPPDATA=os.path.join(home, "local"))
    for k in ("BIGHAT_DB_DIR", "BIGHAT_DATA_DIR", "BIGHAT_FILES_DIR", "BIGHAT_BACKUPS_DIR"):
        env.pop(k, None)
    os.makedirs(os.path.join(home, "Documents"), exist_ok=True)
    log = open(os.path.join(home, "backend.log"), "wb")
    proc = subprocess.Popen([exe], env=env, stdout=log, stderr=subprocess.STDOUT)
    bad = []
    try:
        for _ in range(120):
            try:
                if call(port, "GET", "/health", timeout=3)[0] == 200:
                    break
            except Exception:                                  # noqa: BLE001
                pass
            if proc.poll() is not None:
                bad.append(f"backend exited early (code {proc.returncode})"); break
            time.sleep(1)
        else:
            bad.append("backend did not become healthy in 120 s")
        if not bad:
            st, body = call(port, "GET", "/api/diagnostics/routers")
            if st != 200:
                bad.append(f"/api/diagnostics/routers answered {st}")
            else:
                failed = json.loads(body).get("failed", [])
                for f in failed:
                    bad.append(f"router failed to load: {f['router']}: {f['error']}")
            st, body = call(port, "GET", "/api/scoreboard/scores/local")
            if st != 200 or '"files"' not in body:
                bad.append(f"GET /api/scoreboard/scores/local -> {st} {body[:120]}")
            st, body = call(port, "POST", "/api/scoreboard/scores/import")
            if "api_route_not_found" in body:
                bad.append(f"POST /api/scoreboard/scores/import -> route missing: {body[:120]}")
            st, body = call(port, "POST", "/api/scores/save", {
                "locationName": "Smoke Bar", "presentationName": "Smoke", "presentationDate": "10/20/2026", "presentationId": "smoke",
                "teams": [{"name": "A", "swag": "", "roundScores": [1], "total": 1}], "rounds": [{"label": "R1", "multiplier": 1}]})
            if st != 200:
                bad.append(f"POST /api/scores/save -> {st} {body[:120]}")
            st, body = call(port, "GET", "/api/scoreboard/scores/local")
            if st == 200 and '"Smoke' not in body and "Smoke_Bar" not in body:
                bad.append("Save & Exit then Fetch: the saved night is not in the list")
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:                                      # noqa: BLE001
            proc.kill()
        log.close()
    if bad:
        print("FROZEN BACKEND SMOKE TEST FAILED:")
        for b in bad:
            print("  -", b)
        print("--- last log lines ---")
        print("".join(open(os.path.join(home, "backend.log"), errors="replace").readlines()[-25:]))
        return 1
    print("frozen backend smoke test passed: healthy, no failed routers, scoreboard answers, Save & Exit -> Fetch round-trips")
    shutil.rmtree(home, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
