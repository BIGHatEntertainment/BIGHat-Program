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
    # The scoreboard VIDEO sits behind the standalone-owner gate (story_generator_enabled). Give this throw-away copy the same stored record an
    # activated PC has, so the gate stays fully enforced in the app and the video route can still be tested here.
    os.makedirs(os.path.join(home, "appdata"), exist_ok=True)
    cfg_path = os.path.join(home, "appdata", "system_config.json")
    if not os.path.exists(cfg_path):
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump({"subscription": {"active": True, "tier": "standalone", "owns_standalone": True, "story_generator_enabled": True}}, fh)
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
            # v32.4.0: the ORGANIZATION LOGIN hook must not break the normal login inside the packaged app. An unlinked PC must still say a plain
            # "Invalid email or password" for a stranger (never a 500), and must never ask the Cloud.
            st, body = call(port, "POST", "/api/auth/login", {"email": "stranger@example.com", "password": "not-a-real-password"}, timeout=30)
            if st != 401 or "Invalid email or password" not in body:
                bad.append(f"POST /api/auth/login for a stranger should be 401 'Invalid email or password': {st} {body[:140]}")
            # v32.3.0: the Cloud FILE pull. Its status route must answer inside the packaged app, and an unlinked PC must wait quietly
            # (the module imports the location and .bighat code lazily, so a missing piece shows up here and nowhere else).
            st, body = call(port, "GET", "/api/native/system/cloud-link/files-status", timeout=20)
            if st != 200 or '"state"' not in body:
                bad.append(f"GET /api/native/system/cloud-link/files-status -> {st} {body[:120]}")
            st, body = call(port, "POST", "/api/native/system/cloud-link/files-sync-now", {}, timeout=40)
            if st != 200 or '"not_linked"' not in body:
                bad.append(f"POST files-sync-now on an unlinked PC should say not_linked: {st} {body[:140]}")
            # v32.2.1: the Update tool's green button. It must answer (not 404/500) inside the packaged app. When the channel says an update
            # exists it must hand back a link on this program's own GitHub releases; when current it must say so. Offline: skip, never fail the build.
            st, body = call(port, "POST", "/api/native/updates/open-installer", {}, timeout=40)
            if st in (404, 405) or '"api_route_not_found"' in body:
                bad.append(f"POST /api/native/updates/open-installer -> route missing: {st} {body[:120]}")
            elif st == 200:
                try:
                    u = json.loads(body)
                except ValueError:
                    u = {}
                if u.get("update_available") and not str(u.get("url", "")).startswith("https://github.com/BIGHatEntertainment/BIGHat-Program/releases/"):
                    bad.append(f"update button link is not on this program's releases: {body[:160]}")
            elif st not in (502, 503):
                bad.append(f"POST /api/native/updates/open-installer -> {st} {body[:120]}")
            # v32.1.10: the scoreboard video is drawn in the packaged app (bundled font + ffmpeg), 9:16, with every team
            st, body = call(port, "POST", "/api/scoreboard/generate-video", {
                "teams": [{"name": f"Team {i + 1}", "total": 50 - i, "roundScores": [5, 6, 7, 8, 9, 10]} for i in range(7)],
                "location": "Smoke Bar", "date": "10/20/2026", "aspectRatio": "portrait", "duration": 6,
                "rounds": [{"label": l, "multiplier": 1} for l in ("MC", "REG", "BIG", "MISC", "MYS", "BIG")]}, timeout=240)
            try:
                v = json.loads(body)
            except ValueError:
                v = {}
            if st != 200 or not v.get("success"):
                bad.append(f"POST /api/scoreboard/generate-video -> {st} {body[:160]}")
            elif (v.get("width"), v.get("height"), v.get("teams")) != (1080, 1920, 7) or v.get("size", 0) < 20000:
                bad.append(f"scoreboard video is not a real 1080x1920 file with 7 teams: {v}")
            else:
                st2, _ = call(port, "GET", v["url"], timeout=60)
                if st2 != 200:
                    bad.append(f"the finished video cannot be downloaded: GET {v['url']} -> {st2}")
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
    print("frozen backend smoke test passed: healthy, no failed routers, scoreboard answers, Save & Exit -> Fetch round-trips, scoreboard video is drawn and downloads")
    shutil.rmtree(home, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
