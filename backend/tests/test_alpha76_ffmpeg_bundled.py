"""alpha.76: video features must not need ffmpeg installed on the PC (the installed app carries its own)."""
import os, re, shutil, subprocess, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def no_system_ffmpeg(monkeypatch):
    """Behave like a Windows PC with no ffmpeg installed."""
    monkeypatch.setenv("BIGHAT_IGNORE_SYSTEM_FFMPEG", "1")
    monkeypatch.delenv("BIGHAT_FFMPEG", raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join(d for d in os.environ["PATH"].split(os.pathsep) if not (Path(d) / "ffmpeg").exists()))
    from native import media_tools
    media_tools._cache.clear()
    yield media_tools
    media_tools._cache.clear()


def test_a_bare_ffmpeg_call_really_fails_without_a_system_ffmpeg(no_system_ffmpeg):
    assert shutil.which("ffmpeg") is None
    with pytest.raises(FileNotFoundError):                       # on Windows this is [WinError 2], the bug you hit
        subprocess.run(["ffmpeg", "-version"], capture_output=True)


def test_the_bundled_ffmpeg_is_found_and_runs(no_system_ffmpeg):
    mt = no_system_ffmpeg
    p = mt.ffmpeg_path()
    assert p != "ffmpeg" and os.path.isfile(p) and "imageio_ffmpeg" in p
    assert mt.ffmpeg_ok() is True
    r = mt.run(["ffmpeg", "-version"], capture_output=True, text=True)     # the swap for a leading 'ffmpeg'
    assert r.returncode == 0 and "ffmpeg version" in r.stdout


def test_the_bundled_ffmpeg_can_make_the_story_video_format(no_system_ffmpeg, tmp_path):
    mt = no_system_ffmpeg
    out = tmp_path / "t.mp4"
    r = mt.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=540x960:d=1:r=25", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)], capture_output=True, text=True)
    assert r.returncode == 0 and out.stat().st_size > 500
    assert mt.probe_size(str(out)) == (540, 960)


def test_probe_size_handles_a_missing_or_broken_file(no_system_ffmpeg, tmp_path):
    mt = no_system_ffmpeg
    assert mt.probe_size(str(tmp_path / "nope.mp4")) is None
    bad = tmp_path / "bad.mp4"; bad.write_bytes(b"not a video")
    assert mt.probe_size(str(bad)) is None


def test_a_system_ffmpeg_is_still_preferred_when_present(monkeypatch):
    from native import media_tools as mt
    monkeypatch.delenv("BIGHAT_IGNORE_SYSTEM_FFMPEG", raising=False)
    monkeypatch.delenv("BIGHAT_FFMPEG", raising=False)
    mt._cache.clear()
    if not shutil.which("ffmpeg"):
        pytest.skip("no system ffmpeg here")
    assert mt.ffmpeg_path() == shutil.which("ffmpeg")
    mt._cache.clear()


def test_no_video_code_calls_a_bare_ffmpeg_any_more():
    """Every ffmpeg launch must go through native.media_tools, or it breaks on a PC."""
    bad = []
    for f in ("routes/story_generator.py", "routes/scoreboard.py", "story_generator_service.py"):
        text = (ROOT / f).read_text(encoding="utf-8")
        for n, line in enumerate(text.splitlines(), 1):
            if re.search(r"subprocess\.(run|Popen|check_output|call)\(", line) and "apt-get" not in text.splitlines()[min(n, len(text.splitlines()) - 1)]:
                ctx = " ".join(text.splitlines()[n - 1:n + 3])
                if "ffmpeg" in ctx or "ffprobe" in ctx:
                    bad.append(f"{f}:{n}")
    assert bad == [], bad
    assert "ffprobe" not in (ROOT / "routes/scoreboard.py").read_text(encoding="utf-8").replace("ffprobe is not bundled", "")


def test_the_installer_build_packs_the_ffmpeg_program():
    build = (ROOT.parent / "scripts" / "build_sidecar.py").read_text(encoding="utf-8")
    assert '"--collect-all", "imageio_ffmpeg"' in build                       # without this the .exe is left out of the installer
    req = (ROOT / "requirements-desktop.txt").read_text(encoding="utf-8")
    assert re.search(r"^imageio-ffmpeg==", req, re.M)


def test_the_story_health_check_uses_the_bundled_ffmpeg(no_system_ffmpeg):
    import routes.story_generator as sg
    assert sg._ffmpeg_ok() is True
