"""HTML landing page served at `/download` on api.bighat.live.

The Squarespace store "Get the app" button should point here (or to
`/api/downloads/auto` for a direct redirect). The page:

  * Detects OS on the server from User-Agent and renders the primary
    download button accordingly (Windows .exe / macOS .dmg).
  * Also shows the "other platforms" panel so an Intel Mac user (or a
    Windows user on a Mac browsing the site) can still get the right
    installer.
  * Pulls the latest version + asset URLs live from GitHub's
    `releases/latest` via downloads_resolver.

Self-contained HTML/CSS — no React, no external assets — so it renders
even if bighat.live itself is down."""
from __future__ import annotations

import html
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from . import downloads_resolver

router = APIRouter(tags=["downloads-landing"])


_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Download BIG Hat Entertainment</title>
<link rel="icon" href="data:,">
<style>
  :root {{
    --bg:#0a1428; --panel:#0f1d3a; --line:rgba(251,221,104,0.15);
    --ink:#e5edff; --muted:#8892b0; --accent:#fbdd68; --accent-ink:#1a1a1a;
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; background:var(--bg) radial-gradient(1200px 600px at 10% -10%, rgba(251,221,104,0.06), transparent 60%)
                          radial-gradient(800px 400px at 110% 110%, rgba(80,140,255,0.07), transparent 60%);
    color:var(--ink); font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial;
    min-height:100vh; display:flex; align-items:center; justify-content:center; padding:48px 16px;
  }}
  .wrap {{ width:100%; max-width:760px; }}
  .brand {{
    display:flex; align-items:center; gap:14px; margin-bottom:32px; letter-spacing:0.5px;
  }}
  .brand .dot {{ width:14px; height:14px; border-radius:50%; background:var(--accent); box-shadow:0 0 24px var(--accent); }}
  .brand h1 {{ margin:0; font-size:20px; font-weight:600; }}
  .panel {{
    background:var(--panel); border:1px solid var(--line); border-radius:18px;
    padding:40px 36px; box-shadow:0 30px 80px rgba(0,0,0,0.5);
  }}
  h2 {{ margin:0 0 12px; font-size:34px; line-height:1.1; font-weight:700; }}
  p.lead {{ margin:0 0 28px; color:var(--muted); font-size:15px; max-width:50ch; }}
  .primary {{
    display:inline-flex; align-items:center; gap:10px; padding:18px 26px;
    background:var(--accent); color:var(--accent-ink); border-radius:14px;
    font-weight:700; font-size:17px; text-decoration:none;
    box-shadow:0 12px 30px rgba(251,221,104,0.25);
    transition:transform .15s ease, box-shadow .15s ease;
  }}
  .primary:hover {{ transform:translateY(-1px); box-shadow:0 16px 36px rgba(251,221,104,0.32); }}
  .primary.disabled {{ background:#3a4763; color:var(--muted); cursor:not-allowed; box-shadow:none; pointer-events:none; }}
  .meta {{ margin-top:14px; color:var(--muted); font-size:13px; }}
  hr {{ border:0; border-top:1px solid var(--line); margin:36px 0 24px; }}
  h3 {{ margin:0 0 12px; font-size:13px; font-weight:600; color:var(--muted);
       text-transform:uppercase; letter-spacing:0.12em; }}
  .alts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; }}
  .alt {{
    display:flex; flex-direction:column; gap:4px; padding:14px 16px; border-radius:12px;
    background:rgba(255,255,255,0.02); border:1px solid var(--line); text-decoration:none; color:var(--ink);
    transition: background .15s ease, border-color .15s ease;
  }}
  .alt:hover {{ background:rgba(251,221,104,0.05); border-color:rgba(251,221,104,0.3); }}
  .alt .name {{ font-weight:600; font-size:14px; }}
  .alt .sub  {{ color:var(--muted); font-size:12px; }}
  .alt.disabled {{ opacity:0.45; pointer-events:none; }}
  .banner {{
    background:rgba(255,120,90,0.08); border:1px solid rgba(255,120,90,0.3);
    color:#ffcbb6; padding:12px 16px; border-radius:10px; font-size:13px; margin-bottom:24px;
  }}
  footer {{ margin-top:24px; color:var(--muted); font-size:12px; }}
  footer a {{ color:var(--accent); text-decoration:none; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="brand"><span class="dot"></span><h1>BIG Hat Entertainment</h1></div>
  <div class="panel">
    {missing_banner}
    <h2>{primary_heading}</h2>
    <p class="lead">{primary_blurb}</p>
    {primary_button}
    <hr>
    <h3>Other platforms</h3>
    <div class="alts">{alt_cards}</div>
    <footer>
      Version <strong>{version}</strong> · having trouble? Email
      <a href="mailto:support@bighat.live">support@bighat.live</a>.
    </footer>
  </div>
</div>
</body>
</html>"""


def _platform_label(key: str) -> tuple[str, str]:
    """Return (heading, blurb) for the OS-detected primary block."""
    if key == "windows":
        return ("Download for Windows",
                "Single-installer download with embedded Python and everything you need. "
                "Runs entirely offline after install.")
    if key == "macos_apple":
        return ("Download for Mac (Apple Silicon)",
                "For M1, M2, M3 and newer Macs. Universal disk image — drag the BIG Hat app to Applications and launch.")
    if key == "macos_intel":
        return ("Download for Mac (Intel)",
                "For older Intel-based Macs (pre-2020). Drag the BIG Hat app to Applications and launch.")
    return ("Download BIG Hat Entertainment",
            "Pick the installer for your platform below.")


def _alt_label(key: str) -> tuple[str, str]:
    """(name, sub) for the secondary "other platforms" cards."""
    return {
        "windows":     ("Windows",          "10 / 11 (64-bit)"),
        "macos_apple": ("Mac · Apple Silicon", "M1 / M2 / M3 / M4"),
        "macos_intel": ("Mac · Intel",       "Pre-2020 Macs"),
    }.get(key, (key, ""))


@router.get("/download", response_class=HTMLResponse)
async def download_landing(request: Request, missing: Optional[str] = None):
    """OS-aware landing page. Squarespace store button + bighat.live link
    should both point here."""
    detected = downloads_resolver.detect_platform(request.headers.get("user-agent", ""))
    if detected == "unknown":
        detected = "windows"  # safe-ish default; user can still pick mac below

    # Resolve all three so we can render the primary button + alt cards.
    win  = downloads_resolver.resolve("windows")
    macA = downloads_resolver.resolve("macos_apple")
    macI = downloads_resolver.resolve("macos_intel")
    catalog = {"windows": win, "macos_apple": macA, "macos_intel": macI}

    primary = catalog.get(detected) or {}
    heading, blurb = _platform_label(detected)
    if primary.get("url"):
        primary_btn = (
            f'<a class="primary" href="{html.escape(primary["url"])}" '
            f'data-testid="download-primary-{detected}" download>'
            f'⬇  {html.escape(primary.get("filename") or "Installer")}</a>'
        )
    else:
        primary_btn = (
            '<span class="primary disabled" data-testid="download-primary-missing">'
            'Not yet available for this OS</span>'
        )

    # Alt cards (skip the one we used as primary).
    alt_html_parts: list[str] = []
    for key in ("windows", "macos_apple", "macos_intel"):
        if key == detected:
            continue
        name, sub = _alt_label(key)
        info = catalog[key]
        if info.get("url"):
            alt_html_parts.append(
                f'<a class="alt" href="{html.escape(info["url"])}" '
                f'data-testid="download-alt-{key}" download>'
                f'<span class="name">{html.escape(name)}</span>'
                f'<span class="sub">{html.escape(sub)}</span></a>'
            )
        else:
            alt_html_parts.append(
                f'<div class="alt disabled" data-testid="download-alt-{key}-missing">'
                f'<span class="name">{html.escape(name)}</span>'
                f'<span class="sub">Not yet available</span></div>'
            )
    alt_html = "".join(alt_html_parts) or '<div class="alt disabled">No installers published yet.</div>'

    # Missing-OS banner (set when /api/downloads/auto bounces here).
    banner_html = ""
    if missing:
        name, _ = _alt_label(missing) if missing in {"windows","macos_apple","macos_intel"} else (missing, "")
        banner_html = (
            f'<div class="banner" data-testid="missing-banner">'
            f'We don\'t have a published installer for <strong>{html.escape(name or missing)}</strong> yet. '
            f'Email support@bighat.live and we\'ll let you know the moment it ships.</div>'
        )

    version = (win.get("version") or macA.get("version") or macI.get("version") or "TBD")

    page = _PAGE_TEMPLATE.format(
        missing_banner=banner_html,
        primary_heading=html.escape(heading),
        primary_blurb=html.escape(blurb),
        primary_button=primary_btn,
        alt_cards=alt_html,
        version=html.escape(version),
    )
    return HTMLResponse(content=page, status_code=200)
