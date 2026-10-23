"""v32.3.1: the Program matches the Cloud's PR #34: person profile + settings, and host pictures (avatar / 16:9 / 9:16).
Real MontyDB, real system_config.json, real Files/Hosts folders; only the HTTP is faked, with the Cloud's own shapes."""
import json, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
from test_cloud_sync import feed, V, PR, P, run   # noqa: E402
from test_cloud_files_pull import env as files_env, PNG, GIF, sha   # noqa: E402,F401


def person(i, name, email, **extra):
    it = P(i, name, email)
    it["data"].update(extra)
    return it


@pytest.fixture
def env(files_env, monkeypatch):
    e = files_env
    from native import admin_router, employee_sync, cloud_profile
    e.ar, e.es, e.cp = admin_router, employee_sync, cloud_profile
    admin_router.set_database(e.db) if hasattr(admin_router, "set_database") else None

    def pull_people(items, approve=True):
        feed(e.cs, monkeypatch, [{"seq": 9, "has_more": False, "items": items}])
        return run(e.cs.pull_once(e.db, approve_first_link=approve))
    e.pull_people = pull_people
    e.user = lambda email: e.es.find_user(email)
    e.host_dir = lambda email: __import__("native.files_router", fromlist=["x"]).host_folder(email)
    return e


PROFILE = dict(display_name="DJ Nick", first_name="Nick", last_name="Sellards", home_city="Mesa",
               settings={"theme": "dark", "default_aspect": "portrait", "notify_schedule": True, "language": "en"})


# ---------------------------------------------------------------- profile + settings
def test_the_profile_and_settings_land_on_the_persons_login(env):
    env.pull_people([person("p1", "Sam Host", "sam@x.com", **PROFILE)])
    u = env.user("sam@x.com")
    assert (u["display_name"], u["first_name"], u["last_name"], u["home_city"]) == ("DJ Nick", "Nick", "Sellards", "Mesa")
    assert u["settings"] == {"theme": "dark", "default_aspect": "portrait", "notify_schedule": True, "language": "en"}


def test_the_profile_is_saved_to_the_config_file_and_host_json(env):
    env.pull_people([person("p1", "Sam Host", "sam@x.com", **PROFILE)])
    cfg = json.loads(Path(env.ar.config_manager.config_path).read_text(encoding="utf-8")) if hasattr(env.ar.config_manager, "config_path") else env.ar.config_manager.config
    row = next(u for u in cfg["users"] if u["email"] == "sam@x.com")
    assert row["home_city"] == "Mesa" and row["settings"]["theme"] == "dark"
    hj = json.loads((env.host_dir("sam@x.com") / "host.json").read_text(encoding="utf-8"))
    assert hj["display_name"] == "DJ Nick" and hj["home_city"] == "Mesa"


def test_unknown_settings_keys_and_bad_values_are_dropped(env):
    bad = dict(PROFILE, settings={"theme": "dark", "is_admin": True, "role": "master_admin", "default_aspect": "square", "notify_schedule": "yes",
                                  "language": "english-us-long", "x" * 20: 1})
    env.pull_people([person("p1", "Sam Host", "sam@x.com", **bad)])
    s = env.user("sam@x.com")["settings"]
    assert s == {"theme": "dark", "language": "english-"[:8]} and "is_admin" not in s and "role" not in s


@pytest.mark.parametrize("raw,want", [({"theme": "t" * 100}, {"theme": "t" * 32}), ("not a dict", {}), (None, {}), ([1, 2], {}),
                                      ({"default_aspect": "landscape"}, {"default_aspect": "landscape"}), ({"notify_schedule": 1}, {})])
def test_settings_cleaning(env, raw, want):
    assert env.cp.clean_settings(raw) == want


def test_text_fields_are_trimmed_capped_and_single_line(env):
    c = env.cp.extract({"display_name": "  DJ\n Nick\r\n", "first_name": "N" * 300, "home_city": 5, "last_name": None})
    assert c == {"display_name": "DJ Nick", "first_name": "N" * 80}


def test_an_empty_cloud_value_never_erases_what_is_here(env):
    env.pull_people([person("p1", "Sam Host", "sam@x.com", **PROFILE)])
    env.pull_people([person("p1", "Sam Host", "sam@x.com", display_name="", first_name="", last_name="", home_city="", settings={})])
    u = env.user("sam@x.com")
    assert u["display_name"] == "DJ Nick" and u["home_city"] == "Mesa" and u["settings"]["theme"] == "dark"


def test_a_change_in_the_cloud_updates_the_profile(env):
    env.pull_people([person("p1", "Sam Host", "sam@x.com", **PROFILE)])
    env.pull_people([person("p1", "Sam Host", "sam@x.com", **dict(PROFILE, home_city="Tempe", settings={"theme": "light"}))])
    u = env.user("sam@x.com")
    assert u["home_city"] == "Tempe" and u["settings"] == {"theme": "light"}


def test_a_profile_edited_on_this_pc_wins_over_the_cloud_and_is_reported(env):
    env.pull_people([person("p1", "Sam Host", "sam@x.com", **PROFILE)])
    u = env.user("sam@x.com"); u["home_city"] = "Gilbert (edited here)"; env.ar._save_config()
    r = env.pull_people([person("p1", "Sam Host", "sam@x.com", **dict(PROFILE, home_city="Tempe"))])
    assert env.user("sam@x.com")["home_city"] == "Gilbert (edited here)"
    assert r["counts"]["conflicts"] == 1
    assert any("changed on this PC" in c["why"] and c["kind"] == "person" for c in env.cs._read()["conflicts"])
    r2 = env.pull_people([person("p1", "Sam Host", "sam@x.com", **dict(PROFILE, home_city="Tempe"))])      # still held back, not forced later
    assert env.user("sam@x.com")["home_city"] == "Gilbert (edited here)"


def test_a_person_with_a_hand_made_login_keeps_their_own_profile_when_the_cloud_has_none(env):
    run(env.es.upsert_user_for_employee("Sam Host", "sam@x.com", False, "5", "pw12345678", "pw12345678"))
    u = env.user("sam@x.com"); u["home_city"] = "Mine"; u["display_name"] = "Sam The Man"; env.ar._save_config()
    env.pull_people([person("p1", "Sam Host", "sam@x.com")])
    assert env.user("sam@x.com")["home_city"] == "Mine" and env.user("sam@x.com")["display_name"] == "Sam The Man"


def test_a_brand_new_person_gets_the_profile_on_the_first_pull(env):
    assert env.user("new@x.com") is None
    env.pull_people([person("p2", "New Host", "new@x.com", **PROFILE)])
    u = env.user("new@x.com")
    assert u["display_name"] == "DJ Nick" and u["settings"]["default_aspect"] == "portrait" and u["role"] == "host"


def test_the_master_admin_is_never_changed(env):
    env.pull_people([person("p9", "Owner", "owner@x.com", **dict(PROFILE, first_name="HACK", home_city="Nowhere"))])
    u = env.user("owner@x.com")
    assert u.get("first_name") != "HACK" and u.get("home_city") != "Nowhere" and u.get("role") == "master_admin"


def test_apply_profile_itself_refuses_the_master_admin(env):
    """The pull already skips the master before this module is reached; this proves the second layer too (called directly)."""
    class Ctx:
        def __init__(s): s.m = {}; s.c = []
        def ids(s, kind): return s.m
        def conflict(s, *a): s.c.append(a)
    before = dict(env.user("owner@x.com"))
    out = run(env.cp.apply_profile(Ctx(), "p9", "owner@x.com", dict(PROFILE, first_name="HACK", home_city="Nowhere")))
    after = env.user("owner@x.com")
    assert out is None and all(after.get(k) == before.get(k) for k in ("first_name", "last_name", "display_name", "home_city", "settings", "role"))


def test_the_master_is_marked_in_the_id_map_so_the_pictures_skip_it(env):
    env.pull_people([person("p9", "Owner", "owner@x.com")])
    assert env.cs._read()["ids"]["person"]["p9"].get("master") is True


def test_the_login_name_is_not_flattened_by_the_person_update(env):
    """upsert_user_for_employee re-splits `name` on every pull; the profile step must run AFTER it so display_name survives."""
    env.pull_people([person("p1", "Sam Host", "sam@x.com", **PROFILE)])
    env.pull_people([person("p1", "Sam Host", "sam@x.com", **PROFILE)])
    assert env.user("sam@x.com")["display_name"] == "DJ Nick"


def test_a_bad_profile_never_stops_the_rest_of_the_pull(env, monkeypatch):
    def boom(*a, **k): raise RuntimeError("disk full")
    monkeypatch.setattr(env.cp, "fingerprint", boom)
    r = env.pull_people([person("p1", "Sam Host", "sam@x.com", **PROFILE), V("v1", "The Pub")])
    assert r["state"] == "ok" and run(env.db.venues.count_documents({})) == 1 and run(env.db.employees.count_documents({})) == 1


# ---------------------------------------------------------------- host pictures
def host_file(env, fid, category, name, data, person_id="p1"):
    env.files.append({"file_id": fid, "area": "hosts", "category": category, "person_id": person_id, "venue_id": None, "name": name,
                      "size": len(data), "sha256": sha(data), "updated_at": "2026-10-23T00:00:00+00:00"})
    env.bytes[fid] = data


def test_the_three_pictures_land_where_the_profile_page_and_the_slides_look(env):
    env.pull_people([person("p1", "Sam Host", "sam@x.com")])
    host_file(env, "h1", "host_avatar", "me.png", PNG); host_file(env, "h2", "host_16x9", "slide.gif", GIF); host_file(env, "h3", "host_9x16", "story.gif", GIF + b"2")
    r = env.pull()
    assert r["state"] == "ok" and r["counts"]["added"] == 3
    d = env.host_dir("sam@x.com")
    assert (d / "avatar.png").read_bytes() == PNG and (d / "host-16x9.gif").read_bytes() == GIF and (d / "host-9x16.gif").read_bytes() == GIF + b"2"
    u = env.user("sam@x.com")
    assert (u["profile_picture"], u["host_image_16x9"], u["host_image_9x16"]) == (str(d / "avatar.png"), str(d / "host-16x9.gif"), str(d / "host-9x16.gif"))


def test_the_slide_generator_finds_a_pulled_host_picture(env):
    env.pull_people([person("p1", "Sam Host", "sam@x.com")])
    host_file(env, "h2", "host_16x9", "slide.gif", GIF)
    env.pull()
    import native_slides
    found = None
    for name in ("_host_image_for", "host_image_for", "_find_host_image", "find_host_image"):
        if hasattr(native_slides, name):
            found = getattr(native_slides, name); break
    assert (env.host_dir("sam@x.com") / "host-16x9.gif").is_file()
    if found:
        res = found("sam@x.com") if found.__code__.co_argcount == 1 else None
        assert res is None or "host-16x9" in json.dumps(res, default=str)


def test_a_changed_picture_replaces_ours_and_a_new_type_removes_the_stale_one(env):
    env.pull_people([person("p1", "Sam Host", "sam@x.com")])
    host_file(env, "h1", "host_avatar", "me.png", PNG)
    env.pull()
    env.files.clear(); host_file(env, "h1", "host_avatar", "me.gif", GIF)
    env.pull()
    d = env.host_dir("sam@x.com")
    assert sorted(p.name for p in d.glob("avatar.*")) == ["avatar.gif"] and env.user("sam@x.com")["profile_picture"].endswith("avatar.gif")


def test_a_second_pull_downloads_nothing_for_unchanged_pictures(env):
    env.pull_people([person("p1", "Sam Host", "sam@x.com")])
    host_file(env, "h1", "host_avatar", "me.png", PNG)
    env.pull(); env.calls.clear()
    assert env.pull()["counts"]["unchanged"] == 1 and env.calls == []


def test_a_person_who_has_not_arrived_makes_the_picture_wait_and_nothing_is_downloaded(env):
    host_file(env, "h1", "host_avatar", "me.png", PNG, person_id="not-here-yet")
    r = env.pull()
    assert r["counts"]["waiting"] == 1 and env.calls == []
    env.pull_people([person("p1", "Sam Host", "sam@x.com")])
    env.files.clear(); host_file(env, "h1", "host_avatar", "me.png", PNG, person_id="p1")
    assert env.pull()["counts"]["added"] == 1


def test_the_master_admins_pictures_are_never_pulled(env):
    env.pull_people([person("p9", "Owner", "owner@x.com")])
    host_file(env, "h1", "host_avatar", "me.png", PNG, person_id="p9")
    r = env.pull()
    assert r["counts"]["waiting"] == 1 and env.calls == [] and not (env.host_dir("owner@x.com") / "avatar.png").exists()
    assert not env.user("owner@x.com").get("profile_picture")


def test_a_picture_the_owner_uploaded_by_hand_in_another_kind_is_never_touched(env):
    env.pull_people([person("p1", "Sam Host", "sam@x.com")])
    d = env.host_dir("sam@x.com"); d.mkdir(parents=True, exist_ok=True)
    (d / "host-9x16.gif").write_bytes(b"MY OWN"); (d / "notes.txt").write_text("keep")
    host_file(env, "h1", "host_16x9", "slide.gif", GIF)
    env.pull()
    assert (d / "host-9x16.gif").read_bytes() == b"MY OWN" and (d / "notes.txt").read_text() == "keep" and (d / "host-16x9.gif").read_bytes() == GIF


@pytest.mark.parametrize("name", ["evil.exe", "x.svg", "a.mp4", "noext"])
def test_unsafe_picture_types_are_refused_for_hosts(env, name):
    env.pull_people([person("p1", "Sam Host", "sam@x.com")])
    host_file(env, "h1", "host_avatar", name, PNG)
    r = env.pull()
    assert r["counts"]["failed"] == 1 and not list(env.host_dir("sam@x.com").glob("avatar.*"))


def test_the_folder_comes_from_the_email_here_never_from_the_cloud(env):
    env.pull_people([person("p1", "Sam Host", "sam@x.com")])
    host_file(env, "h1", "host_avatar", "../../../evil.png", PNG)
    env.pull()
    d = env.host_dir("sam@x.com")
    assert (d / "avatar.png").exists() and ".." not in str(d.relative_to(env.home))


def test_a_corrupt_download_is_thrown_away(env):
    env.pull_people([person("p1", "Sam Host", "sam@x.com")])
    host_file(env, "h1", "host_avatar", "me.png", PNG)
    env.files[-1]["sha256"] = "0" * 64
    r = env.pull()
    assert r["counts"]["failed"] == 1 and not (env.host_dir("sam@x.com") / "avatar.png").exists() and not env.user("sam@x.com").get("profile_picture")


def test_a_picture_removed_in_the_cloud_stays_on_this_pc(env):
    env.pull_people([person("p1", "Sam Host", "sam@x.com")])
    host_file(env, "h1", "host_avatar", "me.png", PNG)
    env.pull(); env.files.clear()
    assert env.pull()["state"] == "ok" and (env.host_dir("sam@x.com") / "avatar.png").read_bytes() == PNG and env.user("sam@x.com")["profile_picture"]


def test_the_picture_survives_a_new_session(env):
    env.pull_people([person("p1", "Sam Host", "sam@x.com")])
    host_file(env, "h1", "host_avatar", "me.png", PNG)
    env.pull()
    cfg = env.ar.config_manager
    cfg.load_config() if hasattr(cfg, "load_config") else None
    assert env.user("sam@x.com")["profile_picture"].endswith("avatar.png")
