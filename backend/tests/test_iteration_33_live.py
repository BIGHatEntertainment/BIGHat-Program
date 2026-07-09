"""Iteration 33: Live public URL verification for alpha.56 real-machine fixes."""
import os
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://prototype-ui-audit.preview.emergentagent.com").rstrip("/")


def _get_hosts():
    r = requests.get(f"{BASE}/api/trivia/hosts", timeout=30)
    assert r.status_code == 200, r.text
    hosts = r.json()
    assert isinstance(hosts, list) and hosts, "No hosts returned"
    return hosts


def test_fix1_build_returns_200_with_host_materialization():
    hosts = _get_hosts()
    host_id = hosts[0].get("id") or hosts[0].get("_id")
    payload = {
        "name": "TA Iter33 Build",
        "host_id": host_id,
        "location_id": "anything",
        "round_count": 5,
        "round_files": [
            "MC_Alpha46_Test.bighat",
            "repro-1.bighat",
            "misc-e2e.bighat",
            "mys-e2e.bighat",
            "big-e2e.bighat",
        ],
    }
    r = requests.post(f"{BASE}/api/native/presentations/build", json=payload, timeout=60)
    assert r.status_code == 200, f"build failed: {r.status_code} {r.text[:500]}"
    doc = r.json()
    pres_id = doc.get("id") or doc.get("_id") or (doc.get("presentation") or {}).get("id")
    assert pres_id, f"no presentation id in response: {doc}"
    # persist for next test
    with open("/tmp/iter33_pres_id.txt", "w") as f:
        f.write(pres_id)


def test_fix3_round_2_returns_embedded_cover_data_url():
    with open("/tmp/iter33_pres_id.txt") as f:
        pres_id = f.read().strip()
    r = requests.post(f"{BASE}/api/slide-fetcher/fetch-section/{pres_id}/round_2", timeout=60)
    assert r.status_code == 200, f"fetch-section failed: {r.status_code} {r.text[:500]}"
    data = r.json()
    slides = data.get("slides") or data.get("section", {}).get("slides") or []
    assert slides, f"no slides in section: {list(data.keys())}"
    slide0 = slides[0]
    meta = slide0.get("metadata", {}) or {}
    src_tag = meta.get("_title_card_source") or meta.get("title_card_source")
    assert src_tag == "bighat-embedded-cover", f"unexpected title card source: {src_tag} slide keys={list(slide0.keys())}"
    # find an image element with data:image/jpeg;base64,
    elements = slide0.get("elements") or []
    img_srcs = [e.get("src", "") for e in elements if (e.get("type") == "image" or "src" in e)]
    assert any(s.startswith("data:image/") for s in img_srcs), f"no data-url image element found: {img_srcs[:2]}"


def test_legacy_import_trivia_honors_path_key():
    payload = {
        "userName": "iter33user",
        "host": "H",
        "location": "L",
        "numRounds": 1,
        "rounds": ["/root/Documents/BIG Hat Entertainment/Files/Trivia/REG/repro-1.bighat"],
        "roundTypes": ["REG"],
        "roundNames": ["Repro_1"],
        "presentationName": "TA Legacy Iter33",
        "nativeManifest": {"host": {"name": "H"}, "location": {"name": "L", "slug": "l"}},
    }
    r = requests.post(f"{BASE}/api/presentations/import-trivia", json=payload, timeout=60)
    assert r.status_code == 200, f"import-trivia failed: {r.status_code} {r.text[:500]}"
    body = r.json()
    pres_id = body.get("id") or body.get("_id") or (body.get("presentation") or {}).get("id")
    assert pres_id, f"no id: {body}"

    r2 = requests.post(f"{BASE}/api/slide-fetcher/fetch-section/{pres_id}/round_1", timeout=60)
    assert r2.status_code == 200, r2.text[:500]
    data = r2.json()
    slides = data.get("slides") or data.get("section", {}).get("slides") or []
    assert slides, f"no slides: {list(data.keys())}"
    slide0 = slides[0]
    elements = slide0.get("elements") or []
    img_srcs = [e.get("src", "") for e in elements if "src" in e]
    assert any(s.startswith("data:image/") for s in img_srcs), f"no embedded data-url cover: {img_srcs[:2]}"
