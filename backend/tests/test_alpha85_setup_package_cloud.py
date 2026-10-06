"""alpha.85: cloud Setup Package (one package per master email; no secrets; transfer needs an emailed code)."""
import io, json, zipfile, importlib
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

K1, HW1 = "BHE-AAAA-BBBB-CCCC-DDDD", "pc-1"
K2, HW2 = "BHE-EEEE-FFFF-GGGG-HHHH", "pc-2"       # a second key bought under the SAME email
K3, HW3 = "BHE-1111-2222-3333-4444", "pc-3"       # a different customer


class Lic:
    def __init__(self, email): self.email = email


class FakeColl:
    def __init__(self): self.rows = []
    def _m(self, r, q): return all(r.get(k) == v for k, v in q.items())
    async def insert_one(self, d): self.rows.append(dict(d))
    async def find_one(self, q, proj=None):
        for r in self.rows:
            if self._m(r, q):
                out = dict(r)
                if proj and proj.get("blob") == 0: out.pop("blob", None)
                return out
    async def replace_one(self, q, d):
        for i, r in enumerate(self.rows):
            if self._m(r, q): self.rows[i] = dict(d); return
    async def update_one(self, q, u):
        for r in self.rows:
            if self._m(r, q): r.update(u.get("$set", {})); return
    async def delete_many(self, q): self.rows = [r for r in self.rows if not self._m(r, q)]


class FakeDB:
    def __init__(self): self.setup_packages, self.setup_transfers = FakeColl(), FakeColl()


class Svc:
    revoked = set()
    async def validate(self, *, key, hwid):
        table = {(K1, HW1): "owner@x.com", (K2, HW2): "owner@x.com", (K3, HW3): "other@x.com"}
        if key in self.revoked: return False, "revoked", None
        if (key, hwid) not in table: return False, "hwid_not_activated", None
        return True, "ok", Lic(table[(key, hwid)])


class Mailer:
    def __init__(self): self.sent = []; self.ok = True
    async def _send(self, *, to, subject, html, text):
        self.sent.append({"to": to, "text": text}); return self.ok


@pytest.fixture
def env(monkeypatch):
    from cloud import setup_package_router as sp
    importlib.reload(sp)
    svc, db, mail = Svc(), FakeDB(), Mailer()
    sp.set_runtime(service=svc, db=db, mailer=mail)
    monkeypatch.setattr(sp, "PUBLISH_MIN_SECONDS", 0)
    app = FastAPI(); app.include_router(sp.router)
    return TestClient(app), sp, svc, db, mail


def pkg(extra=None, files=None, doc=None):
    d = doc or {"format": "bighat-setup-package", "format_version": 1,
        "venues": [{"id": "v1", "name": "Monkey Pants", "city": "Phoenix"}], "venue_pricing": [{"venue_id": "v1", "trivia_price": 100}],
        "people": [{"email": "sam@x.com", "name": "Sam", "role": "host"}], "venue_roles": [], "locations": [{"slug": "monkey-pants"}]}
    if extra: d.update(extra)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("package.json", json.dumps(d))
        for n, data in (files or {}).items(): z.writestr(n, data)
    return b.getvalue()


def publish(c, raw, key=K1, hw=HW1, master="1", exp=""):
    return c.post("/api/setup-package/publish", data={"license_key": key, "hwid": hw, "is_master": master, "expected_version": exp, "machine_label": "Office PC"},
                  files={"file": ("p.zip", io.BytesIO(raw))})


def body(key=K1, hw=HW1, **kw): return {"license_key": key, "hwid": hw, **kw}


def test_master_publishes_and_every_copy_pulls_the_same_bytes(env):
    c, sp, svc, db, mail = env
    raw = pkg(files={"images/monkey-pants/logo.png": b"PNG"})
    r = publish(c, raw); assert r.status_code == 200 and r.json()["version"] == 1 and r.json()["counts"]["venues"] == 1
    st = c.post("/api/setup-package/status", json=body()).json(); assert st["exists"] and st["version"] == 1 and st["hash"] == r.json()["hash"]
    got = c.post("/api/setup-package/pull", json=body())
    assert got.status_code == 200 and got.content == raw and got.headers["x-package-version"] == "1"
    assert c.post("/api/setup-package/pull", json=body(K2, HW2)).content == raw          # second key, same email: shares it


def test_a_different_customer_never_sees_it(env):
    c, sp, svc, db, mail = env
    publish(c, pkg())
    assert c.post("/api/setup-package/status", json=body(K3, HW3)).json() == {"exists": False}
    assert c.post("/api/setup-package/pull", json=body(K3, HW3)).status_code == 404


def test_only_real_activated_licenses_and_only_master_publishes(env):
    c, sp, svc, db, mail = env
    assert publish(c, pkg(), key="BHE-ZZZZ-ZZZZ-ZZZZ-ZZZZ").status_code == 401
    assert publish(c, pkg(), hw="stolen-pc").status_code == 401
    assert publish(c, pkg(), master="0").status_code == 403                                # a host's copy cannot publish
    assert c.post("/api/setup-package/pull", json=body(hw="stolen-pc")).status_code == 401
    svc.revoked = {K1}; assert c.post("/api/setup-package/status", json=body()).status_code == 401
    assert db.setup_packages.rows == []


def test_secrets_are_refused_anywhere_in_the_package(env):
    c, sp, svc, db, mail = env
    for bad in ({"people": [{"email": "a@x.com", "password": "x"}]}, {"people": [{"email": "a@x.com", "password_hash": "x"}]},
                {"venues": [{"name": "v", "meta": {"api_key": "x"}}]}, {"people": [{"email": "a@x.com", "Token": "x"}]},
                {"settings": {"license_key": BAD if (BAD := "BHE-AAAA-BBBB-CCCC-DDDD") else ""}}):
        r = publish(c, pkg(bad)); assert r.status_code == 400 and "secret" in r.text, bad
    assert db.setup_packages.rows == []


def test_bad_zips_are_refused(env):
    c, sp, svc, db, mail = env
    assert publish(c, b"not a zip").status_code == 400
    assert publish(c, pkg(files={"../evil.png": b"x"})).status_code == 400                    # path trick
    assert publish(c, pkg(files={"images/x.exe": b"x"})).status_code == 400                   # wrong file type
    assert publish(c, pkg(files={"other/readme.txt": b"x"})).status_code == 400               # outside images/
    assert publish(c, pkg(doc={"format": "something-else"})).status_code == 400
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z: z.writestr("package.json", "{not json")
    assert publish(c, b.getvalue()).status_code == 400
    assert db.setup_packages.rows == []


def test_size_limits(env, monkeypatch):
    c, sp, svc, db, mail = env
    monkeypatch.setattr(sp, "MAX_PACKAGE_MB", 0)
    assert publish(c, pkg()).status_code == 413
    monkeypatch.setattr(sp, "MAX_PACKAGE_MB", 40); monkeypatch.setattr(sp, "MAX_ENTRIES", 2)
    assert publish(c, pkg(files={"images/a.png": b"1", "images/b.png": b"2"})).status_code == 400


def test_versions_count_up_and_a_stale_publish_is_stopped(env):
    c, sp, svc, db, mail = env
    assert publish(c, pkg()).json()["version"] == 1
    assert publish(c, pkg({"venues": []}), exp="1").json()["version"] == 2
    r = publish(c, pkg(), exp="1"); assert r.status_code == 409 and "newer_version_exists:2" in r.text      # someone published meanwhile
    assert c.post("/api/setup-package/status", json=body()).json()["version"] == 2
    assert len(db.setup_packages.rows) == 1


def test_transfer_needs_the_emailed_code(env):
    c, sp, svc, db, mail = env
    publish(c, pkg())
    assert c.post("/api/setup-package/transfer/start", json=body(is_master=False, to_email="new@x.com")).status_code == 403
    assert c.post("/api/setup-package/transfer/start", json=body(is_master=True, to_email="not-an-email")).status_code == 400
    assert c.post("/api/setup-package/transfer/start", json=body(is_master=True, to_email="owner@x.com")).status_code == 400   # same email
    r = c.post("/api/setup-package/transfer/start", json=body(is_master=True, to_email="New@X.com")); assert r.status_code == 200
    assert mail.sent[-1]["to"] == "owner@x.com" and "new@x.com" in mail.sent[-1]["text"]        # code goes to the CURRENT owner, not the target
    code = mail.sent[-1]["text"].split("Confirmation code: ")[1][:6]
    assert "owner@x.com" not in r.text                                                           # response does not reveal the full email
    assert c.post("/api/setup-package/transfer/confirm", json=body(is_master=True, code="000000")).status_code == 400
    assert c.post("/api/setup-package/status", json=body()).json()["exists"]                    # still there
    assert c.post("/api/setup-package/transfer/confirm", json=body(is_master=True, code=code)).json()["moved_to"] == "new@x.com"
    assert c.post("/api/setup-package/status", json=body()).json() == {"exists": False}         # old email no longer has it
    assert db.setup_packages.rows[0]["email"] == "new@x.com"
    assert c.post("/api/setup-package/transfer/confirm", json=body(is_master=True, code=code)).status_code == 400   # code is single use


def test_transfer_locks_after_too_many_wrong_codes_and_needs_email_to_work(env):
    c, sp, svc, db, mail = env
    publish(c, pkg())
    c.post("/api/setup-package/transfer/start", json=body(is_master=True, to_email="new@x.com"))
    code = mail.sent[-1]["text"].split("Confirmation code: ")[1][:6]
    for _ in range(5): c.post("/api/setup-package/transfer/confirm", json=body(is_master=True, code="999999"))
    assert c.post("/api/setup-package/transfer/confirm", json=body(is_master=True, code=code)).status_code == 429       # right code too late: locked
    mail.ok = False
    r = c.post("/api/setup-package/transfer/start", json=body(is_master=True, to_email="new@x.com"))
    assert r.status_code == 503 and db.setup_transfers.rows == []                                  # no email sent => no pending transfer


def test_transfer_cannot_overwrite_an_existing_package(env):
    c, sp, svc, db, mail = env
    publish(c, pkg()); publish(c, pkg(), key=K3, hw=HW3)
    r = c.post("/api/setup-package/transfer/start", json=body(is_master=True, to_email="other@x.com")); assert r.status_code == 409
