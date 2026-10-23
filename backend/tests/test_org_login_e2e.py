"""v32.4.0: the ORGANIZATION LOGIN, end to end. The REAL backend (launcher.py) runs as a process with its own empty home; a small local server
stands in for host.bighat.live and answers POST /api/program/auth/login exactly like BIGHat-Cloud's program_sync_routes.org_login (200 {ok,user},
401 invalid_credentials, 403 deactivated, 429 rate_limited, 402 subscription_lapsed). Every assertion is made over HTTP against /api/auth/login."""
import json, os, socket, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import pytest

BACKEND = Path(__file__).resolve().parents[1]
KEY = "prog-key"
ORG = {   # the Cloud's users for this organization (password in the clear only here, in the fake)
    "owner@org.com": {"password": "OwnerCloudPw1", "name": "Olive Owner", "role": "account_owner", "active": True, "is_admin": True, "phone": "555-0001"},
    "host@org.com": {"password": "HostCloudPw1", "name": "Hank Host", "role": "host", "active": True, "is_admin": False, "phone": "555-0002"},
    "both@org.com": {"password": "CloudSidePw1", "name": "Bea Both", "role": "host", "active": True, "is_admin": False, "phone": ""},
    "gone@org.com": {"password": "GonePw12345", "name": "Gil Gone", "role": "host", "active": False, "is_admin": False, "phone": ""},
    "adminhost@org.com": {"password": "AdminHostPw1", "name": "Ada Min", "role": "host", "active": True, "is_admin": True, "phone": ""},
    "platform@bighat.live": {"password": "PlatformPw12", "name": "Platform", "role": "master_admin", "active": True, "is_admin": True, "phone": ""},
}


class Cloud(BaseHTTPRequestHandler):
    calls = []
    items = []
    mode = {"lapsed": False, "limited": False, "down": False}

    def log_message(self, *a): pass

    def _send(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        if self.headers.get("Authorization") != f"Bearer {KEY}":
            return self._send(401, {"error": "unauthorized"})
        if self.path.startswith("/api/program/whoami"):
            return self._send(200, {"account_id": "a1", "program_id": "p1", "status": "linked"})
        if self.path.startswith("/api/program/changes"):
            return self._send(200, {"seq": 1, "has_more": False, "items": list(Cloud.items)})
        if self.path.startswith("/api/program/manifest"):
            return self._send(200, {"files": [], "count": 0})
        self._send(404, {"error": "not_found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0); body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/program/announce": return self._send(200, {"status": "linked"})
        if self.path == "/api/program/claim-token": return self._send(200, {"status": "linked", "token": KEY, "program_id": "p1"})
        if self.path != "/api/program/auth/login": return self._send(404, {"error": "not_found"})
        Cloud.calls.append((body.get("email"), body.get("password")))
        if self.headers.get("Authorization") != f"Bearer {KEY}": return self._send(401, {"error": "unauthorized"})
        if self.mode["lapsed"]: return self._send(402, {"error": "subscription_lapsed"})
        if self.mode["limited"]: return self._send(429, {"error": "rate_limited"})
        u = ORG.get(str(body.get("email", "")).strip().lower())
        if not u or u["password"] != body.get("password") or u["role"] not in ("account_owner", "host"):
            return self._send(401, {"error": "invalid_credentials"})
        if not u["active"]: return self._send(403, {"error": "deactivated"})
        self._send(200, {"ok": True, "user": {"email": body["email"].strip().lower(), "name": u["name"], "role": u["role"], "is_admin": u["is_admin"], "phone": u["phone"]}})


def _port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class App:
    def __init__(self, linked=True):
        self.home = tempfile.mkdtemp(prefix="orgl_")
        Cloud.calls = []; Cloud.items = []; Cloud.mode.update(lapsed=False, limited=False, down=False)
        self.cloud = HTTPServer(("127.0.0.1", _port()), Cloud)
        threading.Thread(target=self.cloud.serve_forever, daemon=True).start()
        self.port = _port(); self.linked = linked
        os.makedirs(self.home + "/appdata", exist_ok=True); os.makedirs(self.home + "/Documents", exist_ok=True)
        self.cfg_path = self.home + "/appdata/system_config.json"
        import bcrypt
        h = lambda p: bcrypt.hashpw(p.encode(), bcrypt.gensalt(4)).decode()
        json.dump({"setup_complete": True, "license_status": {"key": "BIGHAT-TEST-KEY-0001"}, "subscription": {"active": True, "owns_standalone": True},
                   "users": [
                       {"id": "m1", "email": "master@pc.com", "role": "master_admin", "is_master": True, "password_hash": h("MasterLocal1"), "first_name": "Master", "auth_method": "local", "enabled": True},
                       {"id": "l1", "email": "both@org.com", "role": "host", "is_master": False, "password_hash": h("ProgramSidePw1"), "first_name": "Bea", "auth_method": "local", "enabled": True},
                       {"id": "l2", "email": "localonly@pc.com", "role": "host", "is_master": False, "password_hash": h("LocalOnlyPw1"), "first_name": "Lou", "auth_method": "local", "enabled": True},
                   ]}, open(self.cfg_path, "w"))
        env = dict(os.environ, HOME=self.home, USERPROFILE=self.home, LOCALAPPDATA=self.home + "/l", BIGHAT_PORT=str(self.port), BIGHAT_DATA_ROOT=self.home + "/appdata",
                   BIGHAT_CONFIG_PATH=self.cfg_path, BIGHAT_CLOUD_BASE_URL=f"http://127.0.0.1:{self.cloud.server_port}", BIGHAT_NO_BROWSER="1")
        self.log = open(self.home + "/log.txt", "w")
        self.proc = subprocess.Popen([sys.executable, str(BACKEND / "launcher.py")], cwd=str(BACKEND), env=env, stdout=self.log, stderr=subprocess.STDOUT)
        for _ in range(90):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=2); break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError("backend did not start: " + open(self.home + "/log.txt").read()[-800:])
        if linked:
            self.post("/api/native/system/cloud-link/check", {})

    def post(self, path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", json.dumps(body).encode(), {"content-type": "application/json"})
        try:
            r = urllib.request.urlopen(req, timeout=60); return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try: return e.code, json.loads(e.read() or b"{}")
            except Exception: return e.code, {}

    def login(self, email, pw, copy=False): return self.post("/api/auth/login", {"email": email, "password": pw, "copy_account": copy})
    def users(self): return {u["email"]: u for u in json.load(open(self.cfg_path))["users"]}
    def stop(self):
        self.proc.terminate()
        try: self.proc.wait(10)
        except Exception: self.proc.kill()
        self.cloud.shutdown()


@pytest.fixture
def app():
    """A fresh backend, a fresh empty home and a fresh fake Cloud for EVERY test, so what one test saves can never leak into the next."""
    import copy
    saved = copy.deepcopy(ORG)
    a = App()
    yield a
    a.stop()
    ORG.clear(); ORG.update(saved)


def test_the_backend_is_linked_to_the_fake_cloud(app):
    st = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{app.port}/api/native/system/cloud-link/status").read())
    assert st.get("linked") is True or st.get("state") in ("linked", "ok") or "linked" in json.dumps(st).lower()


# ------------------------------------------------------------------ a Cloud person with NO account on this PC
def test_a_cloud_host_signs_in_with_the_cloud_password_and_nothing_is_saved_unless_they_say_so(app):
    st, r = app.login("host@org.com", "HostCloudPw1")
    assert st == 200 and r["role"] == "host" and r["name"] == "Hank Host" and r["token"] and r["offer_copy"] is True and r["saved_on_this_pc"] is False
    assert "host@org.com" not in app.users()                                      # a one-visit sign-in leaves nothing behind
    assert Cloud.calls == [("host@org.com", "HostCloudPw1")]


def test_copy_my_account_creates_a_local_cloud_account_with_the_same_password(app):
    st, r = app.login("host@org.com", "HostCloudPw1", copy=True)
    assert st == 200 and r["saved_on_this_pc"] is True and r["offer_copy"] is False
    u = app.users()["host@org.com"]
    assert u["auth_method"] == "cloud" and u["role"] == "host" and u["is_master"] is False and u["first_name"] == "Hank" and u["last_name"] == "Host"
    assert "HostCloudPw1" not in json.dumps(u) and u["password_hash"].startswith("$2")        # only a bcrypt hash, never the password


def test_the_account_owner_becomes_a_local_admin_never_a_master(app):
    st, r = app.login("owner@org.com", "OwnerCloudPw1", copy=True)
    u = app.users()["owner@org.com"]
    assert st == 200 and r["role"] == "admin" and u["role"] == "admin" and u["is_admin"] is True and u["is_master"] is False and u["phone"] == "555-0001"


def test_a_host_the_owner_made_admin_on_the_cloud_is_admin_here(app):
    st, r = app.login("adminhost@org.com", "AdminHostPw1")
    assert st == 200 and r["role"] == "admin"


def test_a_wrong_cloud_password_is_refused(app):
    st, r = app.login("owner@org.com", "nope-nope-nope")
    assert st == 401 and "token" not in r and "owner@org.com" not in app.users()


def test_a_deactivated_cloud_user_is_refused_with_a_clear_message(app):
    st, r = app.login("gone@org.com", "GonePw12345")
    assert st == 403 and "deactivated" in json.dumps(r).lower() and "gone@org.com" not in app.users()


def test_the_platform_master_admin_can_never_sign_in_here(app):
    st, r = app.login("platform@bighat.live", "PlatformPw12")
    assert st == 401 and "token" not in r and "platform@bighat.live" not in app.users()


def test_an_unknown_person_is_refused(app):
    assert app.login("nobody@x.com", "whatever12345")[0] == 401


# ------------------------------------------------------------------ the LOCAL login is first and unchanged
def test_a_local_user_with_the_right_password_never_touches_the_cloud(app):
    st, r = app.login("localonly@pc.com", "LocalOnlyPw1")
    assert st == 200 and Cloud.calls == []


def test_the_local_master_admin_signs_in_locally_and_never_touches_the_cloud(app):
    st, r = app.login("master@pc.com", "MasterLocal1")
    assert st == 200 and r["role"] == "master_admin" and Cloud.calls == []


def test_a_hand_made_program_accounts_wrong_password_is_never_sent_to_the_cloud(app):
    st, r = app.login("localonly@pc.com", "guess-guess-1")
    assert st == 401 and Cloud.calls == []


def test_a_wrong_password_for_the_master_admin_is_never_sent_to_the_cloud(app):
    assert app.login("master@pc.com", "OwnerCloudPw1")[0] == 401 and Cloud.calls == []


def test_a_person_with_both_accounts_keeps_the_program_password_working_locally(app):
    st, r = app.login("both@org.com", "ProgramSidePw1")
    assert st == 200 and Cloud.calls == []


def test_a_person_with_both_accounts_and_different_passwords_gets_a_clear_refusal_for_the_cloud_one(app):
    """Documented limit: a hand-made program account's other password is not guessed against the Cloud (no extra guessing surface)."""
    st, r = app.login("both@org.com", "CloudSidePw1")
    assert st == 401 and Cloud.calls == []


# ------------------------------------------------------------------ a copied Cloud account is checked EVERY time
def test_a_copied_cloud_account_asks_the_cloud_every_time(app):
    app.login("host@org.com", "HostCloudPw1", copy=True); Cloud.calls.clear()
    assert app.login("host@org.com", "HostCloudPw1")[0] == 200 and app.login("host@org.com", "HostCloudPw1")[0] == 200
    assert len(Cloud.calls) == 2


def test_a_copied_account_is_refused_when_the_cloud_says_no_even_with_the_old_local_password(app):
    app.login("host@org.com", "HostCloudPw1", copy=True)
    ORG["host@org.com"]["password"] = "ChangedOnCloud9"
    try:
        st, r = app.login("host@org.com", "HostCloudPw1")                          # the OLD password, which the local copy still has
        assert st == 401 and "token" not in r
        st2, r2 = app.login("host@org.com", "ChangedOnCloud9")                      # the NEW one works and the local copy follows it
        assert st2 == 200
        ORG["host@org.com"]["password"] = "HostCloudPw1"
    finally:
        ORG["host@org.com"]["password"] = "HostCloudPw1"


def test_a_deactivated_copied_account_is_locked_out_at_once(app):
    app.login("host@org.com", "HostCloudPw1", copy=True)
    ORG["host@org.com"]["active"] = False
    try:
        st, r = app.login("host@org.com", "HostCloudPw1")
        assert st == 403 and "token" not in r
    finally:
        ORG["host@org.com"]["active"] = True


def test_a_copied_account_cannot_sign_in_when_the_cloud_is_unreachable(app):
    app.login("host@org.com", "HostCloudPw1", copy=True)
    app.cloud.shutdown(); app.cloud.server_close()
    try:
        st, r = app.login("host@org.com", "HostCloudPw1")
        assert st == 503 and "Can't reach" in json.dumps(r) and "token" not in r
    finally:
        pass


def test_the_local_master_admin_still_signs_in_when_the_cloud_is_down(app):
    st, r = app.login("master@pc.com", "MasterLocal1")
    assert st == 200


def test_a_hand_made_local_user_still_signs_in_when_the_cloud_is_down(app):
    assert app.login("localonly@pc.com", "LocalOnlyPw1")[0] == 200


# ------------------------------------------------------------------ a person the Cloud PULL made here (temporary password) -- the "different passwords" case
def _pulled(app, email="host@org.com", name="Hank Host"):
    Cloud.items = [{"kind": "person", "item_id": "p1", "deleted": False, "seq": 1,
                    "data": {"name": name, "email": email, "phone": "", "is_admin": False, "role": "host"}}]
    app.post("/api/native/system/cloud-link/sync-now", {})
    app.post("/api/native/system/cloud-link/sync-approve", {})
    assert email in app.users(), "the data pull did not create the person"


def test_a_person_the_cloud_pull_made_signs_in_with_their_cloud_password_and_the_local_password_follows(app):
    _pulled(app)
    before = app.users()["host@org.com"]["password_hash"]
    st, r = app.login("host@org.com", "HostCloudPw1")
    u = app.users()["host@org.com"]
    assert st == 200 and r["saved_on_this_pc"] is True and u["auth_method"] == "cloud" and u["password_hash"] != before
    import bcrypt
    assert bcrypt.checkpw(b"HostCloudPw1", u["password_hash"].encode())                    # the SAME password now works in both places


def test_a_pulled_persons_wrong_password_is_refused_and_does_not_change_anything(app):
    _pulled(app)
    before = app.users()["host@org.com"]
    st, r = app.login("host@org.com", "not-the-password-1")
    assert st == 401 and app.users()["host@org.com"]["password_hash"] == before["password_hash"] and app.users()["host@org.com"]["auth_method"] == before["auth_method"]


def test_a_pulled_person_with_a_hand_made_local_password_is_never_rewritten_by_a_cloud_sign_in(app):
    """both@org.com is a HAND-MADE program account; the pull adopts that person but must never overwrite their program password."""
    Cloud.items = [{"kind": "person", "item_id": "pb", "deleted": False, "seq": 1, "data": {"name": "Bea Both", "email": "both@org.com", "phone": "", "is_admin": False, "role": "host"}}]
    app.post("/api/native/system/cloud-link/sync-now", {}); app.post("/api/native/system/cloud-link/sync-approve", {})
    before = app.users()["both@org.com"]["password_hash"]
    assert app.login("both@org.com", "ProgramSidePw1")[0] == 200
    assert app.login("both@org.com", "CloudSidePw1")[0] == 401
    assert app.users()["both@org.com"]["password_hash"] == before and app.users()["both@org.com"]["auth_method"] == "local"


# ------------------------------------------------------------------ trouble
def test_a_rate_limited_cloud_says_try_again_later(app):
    Cloud.mode["limited"] = True
    st, r = app.login("host@org.com", "HostCloudPw1")
    assert st == 429 and "15 minutes" in json.dumps(r)


def test_a_lapsed_subscription_says_so(app):
    Cloud.mode["lapsed"] = True
    st, r = app.login("host@org.com", "HostCloudPw1")
    assert st == 503 and "lapsed" in json.dumps(r).lower()


def test_an_unlinked_pc_never_calls_the_cloud_and_refuses_cloud_people(tmp_path):
    a = App(linked=False)
    try:
        assert a.login("host@org.com", "HostCloudPw1")[0] == 401 and Cloud.calls == []
        assert a.login("localonly@pc.com", "LocalOnlyPw1")[0] == 200
    finally:
        a.stop()


def test_a_local_account_turned_off_here_cannot_be_revived_by_a_cloud_sign_in(app):
    app.login("host@org.com", "HostCloudPw1", copy=True)
    uid = app.users()["host@org.com"]["id"]
    st, r = app.login("master@pc.com", "MasterLocal1")
    tok = r["token"]
    req = urllib.request.Request(f"http://127.0.0.1:{app.port}/api/native/admin/users/{uid}", json.dumps({"enabled": False}).encode(),
                                 {"content-type": "application/json", "Authorization": f"Bearer {tok}"}, method="PUT")
    assert urllib.request.urlopen(req, timeout=30).status == 200 and app.users()["host@org.com"]["enabled"] is False
    st, r = app.login("host@org.com", "HostCloudPw1")
    assert st == 403 and "token" not in r and "turned off" in json.dumps(r)


def test_the_password_never_appears_in_the_backend_log(app):
    app.login("host@org.com", "HostCloudPw1", copy=True); app.login("owner@org.com", "wrong-pass-123")
    app.log.flush()
    assert "HostCloudPw1" not in open(app.home + "/log.txt").read() and "wrong-pass-123" not in open(app.home + "/log.txt").read()


def test_the_role_vocabulary_matches_the_programs():
    from native import org_login
    assert org_login.role_for_cloud("account_owner") == "admin" and org_login.role_for_cloud("host") == "host"
    for bad in ("master_admin", "admin", "", None, "ACCOUNT_OWNER_X"):
        assert org_login.role_for_cloud(bad) is None
