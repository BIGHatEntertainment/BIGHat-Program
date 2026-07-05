"""
Regression tests for v32.0.0-alpha.47.

Adds Audience View for trivia:
  1. `/trivia/audience` route exists and renders a React component.
  2. `TriviaAudienceView.jsx` uses a 1920×1080 fixed stage with uniform
     `Math.min(vw/STAGE_W, vh/STAGE_H)` scaling so every TV in every bar
     shows the identical layout regardless of physical resolution.
  3. `TriviaAudienceView.jsx` listens on the `bighat-trivia-audience`
     BroadcastChannel for `UPDATE_SLIDE` / `REVEAL_ANSWER` messages.
  4. `PresentationMode.jsx` publishes to the SAME BroadcastChannel via
     `broadcastToAudience()` — no more `document.write` blob.
  5. `openAudienceView` opens the `/trivia/audience` URL (or Tauri
     `WebviewWindow.new` when available) instead of `about:blank`.
"""
from __future__ import annotations

from pathlib import Path

APP = Path("/app/frontend/src")


def test_trivia_audience_view_file_exists():
    p = APP / "pages" / "trivia" / "TriviaAudienceView.jsx"
    assert p.exists(), "alpha.47: TriviaAudienceView.jsx must exist"


def test_audience_route_registered_in_app_js():
    src = (APP / "App.js").read_text()
    assert 'import TriviaAudienceView' in src
    assert '/trivia/audience' in src
    assert '<TriviaAudienceView' in src


def test_audience_view_uses_fixed_1920x1080_stage():
    src = (APP / "pages" / "trivia" / "TriviaAudienceView.jsx").read_text()
    # Constants must be present so every TV renders the identical layout.
    assert "STAGE_W = 1920" in src
    assert "STAGE_H = 1080" in src
    # Uniform scale = min(vw/STAGE_W, vh/STAGE_H) — this is what makes
    # the layout identical across TVs with different physical resolutions.
    assert "Math.min(" in src and "STAGE_W" in src and "STAGE_H" in src
    # Transform: scale + translate for centered stage
    assert "transform:" in src and "scale(" in src


def test_audience_view_uses_broadcast_channel():
    src = (APP / "pages" / "trivia" / "TriviaAudienceView.jsx").read_text()
    assert "BroadcastChannel" in src
    assert "bighat-trivia-audience" in src
    # Message types the host will send
    assert "UPDATE_SLIDE" in src
    assert "REVEAL_ANSWER" in src
    # AUDIENCE_READY announcement so host can push current state on connect
    assert "AUDIENCE_READY" in src


def test_audience_view_has_no_host_chrome():
    """Sanity: no timer, no controls, no reveal button, no score-tracker
    button on the audience view. The audience only sees the slide."""
    src = (APP / "pages" / "trivia" / "TriviaAudienceView.jsx").read_text()
    # These would be host-only UI elements. Match with word boundaries
    # via `import.*Pause` / `<Pause` to avoid catching `autoPlay` etc.
    import re
    audience_src = src
    for host_only, pattern in (
        ('ChevronLeft', r'\bChevronLeft\b'),
        ('ChevronRight', r'\bChevronRight\b'),
        ('Pause icon', r'\bPause\b(?!ference)'),  # match Pause not "pause"-substrings
        ('Score Tracker', r'Score Tracker'),
        ('onOpenScoreTracker', r'onOpenScoreTracker'),
        ('timeRemaining', r'\btimeRemaining\b'),
        ('goNext', r'\bgoNext\b'),
        ('goPrev', r'\bgoPrev\b'),
    ):
        assert not re.search(pattern, audience_src), (
            f"alpha.47: audience view must not contain host-only UI '{host_only}'"
        )


def test_audience_view_ships_with_fullscreen_affordance():
    src = (APP / "pages" / "trivia" / "TriviaAudienceView.jsx").read_text()
    # Bar TVs need fullscreen; browser needs a user-gesture to enter
    # fullscreen, so we always ship a click-to-fullscreen affordance.
    assert "requestFullscreen" in src
    assert "fullscreen" in src.lower()


# ---- PresentationMode wiring ---------------------------------------------

def test_presentation_mode_uses_broadcast_channel():
    src = (APP / "components" / "trivia" / "editor" / "PresentationMode.jsx").read_text()
    assert "BroadcastChannel" in src
    assert "bighat-trivia-audience" in src
    # The single helper that publishes to both BC and legacy postMessage.
    assert "broadcastToAudience" in src


def test_presentation_mode_no_longer_writes_inline_audience_html():
    """The 650-line `document.write` blob is what made the Tauri
    audience-view button do nothing. Alpha.47 replaces it with a
    proper /trivia/audience route."""
    src = (APP / "components" / "trivia" / "editor" / "PresentationMode.jsx").read_text()
    # No document.write calls
    assert "document.write" not in src, (
        "alpha.47 regression: document.write blob must be gone — "
        "audience view is now a real /trivia/audience route"
    )
    # No `about:blank` opener
    assert "'about:blank'" not in src and '"about:blank"' not in src


def test_open_audience_view_targets_the_audience_route():
    src = (APP / "components" / "trivia" / "editor" / "PresentationMode.jsx").read_text()
    # The URL the audience window navigates to
    assert "/trivia/audience" in src
    # Should attempt Tauri WebviewWindow when available (desktop)
    assert "WebviewWindow" in src
    # Should fall back to window.open (browser / preview)
    assert "window.open(" in src


def test_reveal_answer_uses_broadcast_helper_not_direct_postmessage():
    """After the alpha.47 migration, no direct `audienceWindowRef.current
    .postMessage(...)` should remain — every publish must go through
    `broadcastToAudience` so BOTH the BroadcastChannel receiver AND the
    legacy postMessage receiver stay in sync."""
    src = (APP / "components" / "trivia" / "editor" / "PresentationMode.jsx").read_text()
    # The helper itself is allowed to call .postMessage internally.
    fn_start = src.index("const broadcastToAudience")
    fn_end = src.index("}, []);", fn_start) + len("}, []);")
    outside = src[:fn_start] + src[fn_end:]
    # No lingering direct postMessage calls in the rest of the file.
    assert "audienceWindowRef.current.postMessage" not in outside, (
        "alpha.47: all audience postMessage calls must go through "
        "broadcastToAudience()"
    )
