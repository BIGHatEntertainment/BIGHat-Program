"""v32.1.9: in the INSTALLED app the Scoreboard router crashed while loading (it made a folder next to its own file, which is read-only
inside PyInstaller's bundle), so every /api/scoreboard/* call answered not_found. Importing the module must never write beside it,
and a router that fails to load must be listed on /api/diagnostics/routers."""
import importlib, os, sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def reload_scoreboard():
    sys.modules.pop("routes.scoreboard", None)
    return importlib.import_module("routes.scoreboard")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGHAT_DATA_ROOT", str(tmp_path / "appdata"))
    monkeypatch.setenv("BIGHAT_FILES_DIR", str(tmp_path / "docs"))
    return tmp_path


def test_exports_live_in_appdata_not_next_to_the_module(env):
    sb = reload_scoreboard()
    assert sb.EXPORTS_DIR.is_dir() and "scoreboard_exports" in str(sb.EXPORTS_DIR)
    assert Path(sb.__file__).parent not in sb.EXPORTS_DIR.parents and sb.EXPORTS_DIR.parent != Path(sb.__file__).parent
    assert str(env) in str(sb.EXPORTS_DIR)


def test_the_module_loads_even_when_the_folder_beside_it_is_read_only(env, monkeypatch):
    """The exact v32.1.8 failure: any mkdir beside the module raises. The router must still import and mount."""
    real = Path.mkdir
    beside = Path(sys.modules["routes"].__file__).parent if "routes" in sys.modules else Path(__file__).resolve().parents[1] / "routes"
    def guarded(self, *a, **k):
        if beside in (self, *self.parents) and self.name == "exports":
            raise FileNotFoundError(2, "No such file or directory", str(self))
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "mkdir", guarded)
    sb = reload_scoreboard()
    assert sb.router is not None and sb.EXPORTS_DIR.is_dir()


def test_it_falls_back_when_appdata_cannot_be_written(env, monkeypatch):
    real = Path.mkdir
    def deny(self, *a, **k):
        if "scoreboard_exports" in str(self) and "bighat_scoreboard_exports" not in str(self):
            raise PermissionError(13, "denied", str(self))
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "mkdir", deny)
    sb = reload_scoreboard()
    assert sb.EXPORTS_DIR.is_dir() and "bighat_scoreboard_exports" in str(sb.EXPORTS_DIR)


def test_the_router_has_every_route_the_screen_calls(env):
    sb = reload_scoreboard()
    have = {(m, r.path) for r in sb.router.routes for m in r.methods}
    for need in [("GET", "/scoreboard/scores/local"), ("POST", "/scoreboard/scores/import"), ("POST", "/scoreboard/generate-video"),
                 ("POST", "/scoreboard/sharepoint/sync"), ("GET", "/scoreboard/scores"), ("POST", "/scoreboard/exports/upload")]:
        assert need in have, need


def test_router_failures_are_listed_by_the_diagnostics_route():
    """Read server.py as text (importing it needs a database URL): every 'Could not load X routes' handler records the failure,
    and the diagnostics route exists."""
    src = (Path(__file__).resolve().parents[1] / "server.py").read_text()
    assert "_ROUTER_FAILURES: list = []" in src and '"/api/diagnostics/routers"' in src
    skipped = src.count('logger.warning(f"Could not load')
    assert skipped >= 18 and skipped == src.count("_ROUTER_FAILURES.append")          # none can be skipped without being recorded
