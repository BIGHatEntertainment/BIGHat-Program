"""v32.1.10: the scoreboard MP4, drawn like the Trivia Player's FINAL SCORES slide (frontend FinalScoresBoard.jsx).

Why a rewrite: the old renderer used fixed pixel sizes (14-56 px on a 1080/1920 canvas) and a Linux-only font path, so on Windows it fell back to
Pillow's tiny default font, it listed only 10 teams as a still picture and its grid scrolled once every 6 seconds. Here every size is a fraction of the
canvas HEIGHT (the slide uses `vh` the same way), the fonts are found on every PC (never the tiny default), the grid holds still and the team list
scrolls UP over it at the slide's pace (5 s per team, 20-150 s).
"""
from __future__ import annotations

import math
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

GOLD = (251, 221, 104)
FONT_LEMONADA = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "Lemonada-Bold.ttf"

RANK = [  # (fill rgba, border, text, label)  gold / silver / bronze, as the slide
    ((120, 98, 24, 255), (251, 221, 104), (251, 221, 104), "1"),
    ((84, 92, 118, 255), (213, 219, 232), (230, 234, 245), "2"),
    ((92, 56, 26, 255), (205, 127, 50), (224, 160, 100), "3"),
]
REST = ((20, 27, 80, 255), (251, 221, 104, 90), (251, 221, 104, 215))

_BOLD_CANDIDATES = [
    r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\calibrib.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
_MONO_CANDIDATES = [
    r"C:\Windows\Fonts\consolab.ttf", r"C:\Windows\Fonts\courbd.ttf", "/System/Library/Fonts/Menlo.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
]


def _first_font(paths: List[str]) -> Optional[str]:
    for p in paths:
        if os.path.isfile(p):
            return p
    return None


def font_files() -> Dict[str, str]:
    """The font files used, by role. Never empty: Lemonada ships inside the app, so even a PC with none of the others still gets a real font."""
    lem = str(FONT_LEMONADA) if FONT_LEMONADA.is_file() else None
    bold = _first_font(_BOLD_CANDIDATES) or lem
    mono = _first_font(_MONO_CANDIDATES) or bold
    return {"title": lem or bold or "", "bold": bold or "", "mono": mono or ""}


class Fonts:
    def __init__(self) -> None:
        self.files = font_files()
        self._cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}

    def get(self, role: str, px: int) -> ImageFont.FreeTypeFont:
        px = max(8, int(px))
        key = (role, px)
        if key not in self._cache:
            path = self.files.get(role) or self.files.get("bold") or ""
            if not path:
                raise RuntimeError("no usable font found (Lemonada-Bold.ttf missing from the app)")
            try:
                self._cache[key] = ImageFont.truetype(path, px)
            except OSError:
                self._cache[key] = ImageFont.truetype(self.files["title"], px)
        return self._cache[key]


def scroll_seconds(team_count: int) -> int:
    """Same rule as the slide: 5 s per team, never faster than 20 s, never slower than 150 s."""
    return int(min(150, max(20, (int(team_count) or 0) * 5)))


def video_seconds(team_count: int, cap: int = 60) -> int:
    """One full pass of the list, kept short enough to share (the slide loops; a video plays once)."""
    if team_count <= 5:
        return 12
    return int(min(cap, max(20, team_count * 3)))


def _fit(draw: ImageDraw.ImageDraw, text: str, font_get, role: str, px: int, max_w: int) -> Tuple[str, ImageFont.FreeTypeFont]:
    """Shrink (down to 60 %) then cut with '...' so a long name can never run over the score."""
    f = font_get(role, px)
    if draw.textlength(text, font=f) <= max_w:
        return text, f
    for k in (0.9, 0.8, 0.7, 0.6):
        f = font_get(role, px * k)
        if draw.textlength(text, font=f) <= max_w:
            return text, f
    t = text
    while len(t) > 1 and draw.textlength(t + "...", font=f) > max_w:
        t = t[:-1]
    return t.rstrip() + "...", f


def _sky_and_grid(W: int, H: int) -> Image.Image:
    """Still backdrop: navy sky with stars, gold horizon at 50 %, perspective-less grid below (as SynthwaveBackdrop still)."""
    img = Image.new("RGB", (W, H), (0, 14, 42))
    d = ImageDraw.Draw(img)
    stops = [(0.0, (0, 14, 42)), (0.25, (10, 25, 64)), (0.45, (20, 27, 80)), (0.5, (10, 25, 64)), (1.0, (0, 14, 42))]
    for y in range(H):
        t = y / H
        for (a, ca), (b, cb) in zip(stops, stops[1:]):
            if a <= t <= b:
                k = (t - a) / (b - a) if b > a else 0
                d.line([(0, y), (W, y)], fill=tuple(int(ca[i] + (cb[i] - ca[i]) * k) for i in range(3)))
                break
    rnd = random.Random(42)
    for _ in range(60):
        sx, sy = rnd.randint(0, W), rnd.randint(0, int(H * 0.48))
        sr = max(1, int(H * rnd.uniform(0.0006, 0.0016)))
        col = rnd.choice([(89, 115, 247), GOLD, (136, 146, 176), (255, 255, 255)])
        d.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=col)
    hy = H // 2
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i in range(int(H * 0.05)):
        a = 1 - abs(i - H * 0.025) / (H * 0.025)
        if a > 0:
            gd.line([(0, hy - int(H * 0.025) + i), (W, hy - int(H * 0.025) + i)], fill=(int(251 * a * .35), int(221 * a * .35), int(104 * a * .35)))
    img = Image.composite(img, img, Image.new("L", (W, H), 255))
    from PIL import ImageChops
    img = ImageChops.add(img, glow)
    d = ImageDraw.Draw(img)
    grid_h = H - hy
    for i in range(24):
        x = int((i + 0.5) / 24 * W)
        d.line([(x, hy + 3), (x, H)], fill=(24, 32, 78), width=max(1, W // 900))
    sp = max(24, int(H * 0.031))
    y = hy + sp
    while y < H:
        f = min(1.0, (y - hy) / (grid_h * 0.5))
        d.line([(0, y), (W, y)], fill=(int(251 * f * .42), int(221 * f * .42), int(104 * f * .42)), width=max(1, H // 900))
        y += sp
    d.line([(0, hy), (W, hy)], fill=GOLD, width=max(2, H // 640))
    return img


class Layout:
    """All pixel sizes, derived from the canvas height exactly like the slide's vh units."""

    def __init__(self, W: int, H: int) -> None:
        self.W, self.H = W, H
        vh = H / 100.0
        self.vh = vh
        portrait = H > W
        self.pad_x = int(W * (0.06 if not portrait else 0.05))
        self.pad_top = int(H * 0.035)
        self.k = 1.0 if not portrait else 0.78                      # a 9:16 canvas is narrow: keep the same look, a little smaller than 1:1 vh
        s = lambda v: int(v * vh * self.k)                          # noqa: E731
        self.f_kicker, self.f_title, self.f_sub, self.f_chip = s(1.8), s(6.6), s(2.6), s(2.2)
        self.f_rank, self.f_name, self.f_swag, self.f_total, self.f_totlbl = s(4.4), s(3.8), s(1.9), s(6.0), s(1.6)
        self.f_rlabel, self.f_rval, self.f_footer = s(2.2), s(2.9), s(1.8)
        self.box_pad_y, self.box_pad_x, self.box_gap = s(1.6), int(W * 0.022), s(1.4)
        if portrait:                                                # the slide is 16:9; on 9:16 give the title and names more room
            self.f_title = s(5.6)
            self.f_name = s(3.4)


def _team_box(L: Layout, fonts: Fonts, team: Dict[str, Any], idx: int, rounds: List[Dict[str, Any]], width: int) -> Image.Image:
    c = (RANK[idx][0], RANK[idx][1], RANK[idx][2]) if idx < 3 else REST
    fill, border, txt = c
    scores = [s for s in (team.get("roundScores") or [])]
    swag = str(team.get("swag") or "").strip()
    chips_h = int(L.f_rval * 1.9) + int(L.vh) if scores else 0
    name_h = L.f_name + (int(L.f_swag * 1.3) if swag else 0)
    top_h = max(name_h, L.f_total + int(L.f_totlbl * 1.2))
    h = L.box_pad_y * 2 + top_h + (int(L.vh * 1.0) + chips_h if scores else 0)
    img = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = max(8, int(L.vh * 1.4))
    d.rounded_rectangle([0, 0, width - 1, h - 1], radius=r, fill=fill, outline=border, width=max(2, int(L.vh * 0.2)))
    x = L.box_pad_x
    mid = L.box_pad_y + max(name_h, L.f_total) // 2
    label = ("#" + RANK[idx][3]) if idx < 3 else f"{idx + 1}"
    fr = fonts.get("mono", L.f_rank)
    d.text((x, mid), label, font=fr, fill=txt, anchor="lm")
    x += int(L.f_rank * 1.9)                                      # rank column: wide enough for '#1' and '10.', not a wide empty gap
    total = str(team.get("total") or 0)
    ft = fonts.get("mono", L.f_total)
    tw = int(d.textlength(total, font=ft))
    right = width - L.box_pad_x
    d.text((right, L.box_pad_y + L.f_total // 2 - int(L.f_totlbl * 0.4)), total, font=ft, fill=(255, 215, 0), anchor="rm")
    d.text((right, L.box_pad_y + L.f_total + int(L.vh * 0.2)), "Total Points", font=fonts.get("bold", L.f_totlbl), fill=(244, 242, 255, 175), anchor="ra")
    name, fn = _fit(d, str(team.get("name") or f"Team {idx + 1}"), fonts.get, "bold", L.f_name, right - tw - x - int(L.W * 0.03))
    ny = L.box_pad_y + (L.f_name // 2 if not swag else int(L.f_name * 0.5))
    d.text((x, ny + int(L.f_name * 0.05)), name, font=fn, fill=(244, 242, 255), anchor="lm")
    if swag:
        d.text((x, ny + int(L.f_name * 0.62)), swag, font=fonts.get("bold", L.f_swag), fill=(244, 242, 255, 153), anchor="lm")
    if scores:
        cy = h - L.box_pad_y - chips_h + int(L.vh * 0.2)
        cx = x
        avail = width - L.box_pad_x - x
        gap = int(L.vh * 1.0)
        labs = [((rounds[i].get("label") if i < len(rounds) else None) or f"R{i + 1}") + ":" for i in range(len(scores))]
        vals = [str(sc or 0) for sc in scores]
        k = 1.0
        for _ in range(12):                                         # shrink the row until EVERY chip fits on one line; a score is never dropped
            fl, fv = fonts.get("bold", L.f_rlabel * k), fonts.get("bold", L.f_rval * k)
            ws = [d.textlength(a, font=fl) + d.textlength(b, font=fv) + L.vh * 2.4 * k for a, b in zip(labs, vals)]
            if sum(ws) + gap * k * (len(ws) - 1) <= avail or k < 0.45:
                break
            k *= 0.92
        ch = chips_h - int(L.vh * 0.4)
        for a, b, cw in zip(labs, vals, ws):
            cw = int(cw)
            d.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=int(L.vh * 0.8), fill=(0, 0, 20, 200))
            d.text((cx + int(L.vh * 0.8 * k), cy + ch // 2), a, font=fl, fill=(244, 242, 255, 200), anchor="lm")
            d.text((cx + int(L.vh * 0.8 * k) + d.textlength(a, font=fl) + int(L.vh * 0.8 * k), cy + ch // 2), b, font=fv, fill=(255, 255, 255), anchor="lm")
            cx += cw + int(gap * k)
    return img


def _header(L: Layout, fonts: Fonts, location: str, date: str, rounds: List[Dict[str, Any]]) -> Image.Image:
    W = L.W
    img = Image.new("RGBA", (W, int(L.H * 0.3)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = L.pad_top
    d.text((W // 2, y), "BIG HAT TRIVIA", font=fonts.get("bold", L.f_kicker), fill=GOLD, anchor="mt")
    y += int(L.f_kicker * 1.5)
    name, ft = _fit(d, location or "Final Scores", fonts.get, "title", L.f_title, W - 2 * L.pad_x)
    d.text((W // 2 + 2, y + 3), name, font=ft, fill=(0, 0, 0, 160), anchor="mt")
    d.text((W // 2, y), name, font=ft, fill=(255, 255, 255), anchor="mt")
    y += int(ft.size * 1.25)
    sub = "Final Scores" + (f"  -  {date}" if date else "")
    d.text((W // 2, y), sub, font=fonts.get("bold", L.f_sub), fill=GOLD, anchor="mt")
    y += int(L.f_sub * 1.6)
    chips = []
    fc = fonts.get("mono", L.f_chip)
    for r in rounds or []:
        mult = r.get("multiplier") or 1
        txt = f"{r.get('label', '')}" + (f" x{mult}" if mult > 1 else "")
        chips.append((txt, mult > 1, int(d.textlength(txt, font=fc) + L.vh * 2.2)))
    ch = int(L.f_chip * 1.7)
    row_w = sum(w for _, _, w in chips) + int(L.vh * 0.8) * max(0, len(chips) - 1)
    if chips and row_w > W - 2 * L.pad_x:                          # too many chips for one row: keep them on one row at a smaller size
        fc = fonts.get("mono", L.f_chip * (W - 2 * L.pad_x) / row_w * 0.97)
        chips = [(t, m, int(d.textlength(t, font=fc) + L.vh * 1.6)) for t, m, _ in chips]
        row_w = sum(w for _, _, w in chips) + int(L.vh * 0.6) * max(0, len(chips) - 1)
    x = (W - row_w) // 2
    for txt, hot, w in chips:
        d.rounded_rectangle([x, y, x + w, y + ch], radius=int(L.vh * 0.6), fill=(251, 221, 104, 41) if hot else (255, 255, 255, 18),
                            outline=(251, 221, 104, 102) if hot else (255, 255, 255, 26), width=max(1, int(L.vh * 0.12)))
        d.text((x + w // 2, y + ch // 2), txt, font=fc, fill=GOLD if hot else (210, 215, 255, 178), anchor="mm")
        x += w + int(L.vh * 0.8)
    if chips:
        y += ch
    return img.crop((0, 0, W, min(img.height, y + int(L.vh * 1.4))))


def build_scene(W: int, H: int, teams: List[Dict[str, Any]], location: str, date: str, rounds: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Everything that does not change between frames: backdrop, header, footer, the tall strip of team boxes."""
    L, fonts = Layout(W, H), Fonts()
    back = _sky_and_grid(W, H)
    head = _header(L, fonts, location, date, rounds)
    box_w = W - 2 * L.pad_x
    boxes = [_team_box(L, fonts, t, i, rounds, box_w) for i, t in enumerate(teams)]
    strip_h = sum(b.height for b in boxes) + L.box_gap * max(0, len(boxes) - 1)
    strip = Image.new("RGBA", (box_w, max(1, strip_h)), (0, 0, 0, 0))
    y = 0
    for b in boxes:
        strip.alpha_composite(b, (0, y))
        y += b.height + L.box_gap
    foot = Image.new("RGBA", (W, int(L.vh * 5)), (0, 0, 0, 0))
    fd = ImageDraw.Draw(foot)
    r = max(8, int(L.vh * 1.1))
    fd.ellipse([L.pad_x, foot.height // 2 - r, L.pad_x + 2 * r, foot.height // 2 + r], fill=(255, 215, 0, 140))
    fd.text((L.pad_x + 2 * r + int(L.vh * 1.2), foot.height // 2), "BIG Hat Entertainment", font=fonts.get("bold", L.f_footer), fill=(251, 221, 104, 140), anchor="lm")
    top = head.height
    bottom = H - foot.height
    base = back.convert("RGBA")
    base.alpha_composite(head, (0, 0))
    base.alpha_composite(foot, (0, bottom))
    view_h = bottom - top
    mask = Image.new("L", (W, view_h), 255)
    edge = max(1, int(view_h * 0.06))
    md = ImageDraw.Draw(mask)
    for i in range(edge):
        v = int(255 * i / edge)
        md.line([(0, i), (W, i)], fill=v)
        md.line([(0, view_h - 1 - i), (W, view_h - 1 - i)], fill=v)
    return {"L": L, "back": back, "base": base, "head": head, "strip": strip, "foot": foot, "view": (top, bottom), "teams": len(teams),
            "box_w": box_w, "fade_mask": mask}


def frame_at(scene: Dict[str, Any], t: float, seconds: int) -> Image.Image:
    """One frame. The backdrop, header and footer never change, so they are baked ONCE into scene['base']; a frame only blends the moving strip
    (cropped to the part that is on screen) and the fade at the top and bottom of the list area."""
    L: Layout = scene["L"]
    W = L.W
    top, bottom = scene["view"]
    view_h = bottom - top
    strip: Image.Image = scene["strip"]
    base: Image.Image = scene["base"]
    img = base.copy()
    if strip.height <= view_h:                                      # a short list sits centred and still, like the slide
        img.alpha_composite(strip, (L.pad_x, top + (view_h - strip.height) // 2))
        return img.convert("RGB")
    hold_in = min(2.0, seconds * 0.12)                              # read the title and the podium first
    hold_out = min(2.5, seconds * 0.12)                             # and end with the LAST team resting at the bottom (the frame people screenshot)
    p = min(1.0, max(0.0, (t - hold_in) / max(0.001, seconds - hold_in - hold_out)))
    start = int(L.vh * 1.0)
    end = view_h - strip.height - int(L.vh * 1.0)                   # last box's bottom edge just above the footer
    y = int(start + (end - start) * p)                              # strip's top edge inside the list area
    # only the part of the strip that is inside the list area
    src_top, src_bot = max(0, -y), min(strip.height, view_h - y)
    if src_bot > src_top:
        piece = strip.crop((0, src_top, strip.width, src_bot))
        layer = Image.new("RGBA", (W, view_h), (0, 0, 0, 0))
        layer.alpha_composite(piece, (L.pad_x, max(0, y)))
        layer = _fade_edges(layer, scene)
        img.alpha_composite(layer, (0, top))
    # the footer sits above the list: draw it again so the list never covers it
    img.alpha_composite(scene["foot"], (0, bottom))
    return img.convert("RGB")


def _fade_edges(layer: Image.Image, scene: Dict[str, Any]) -> Image.Image:
    """The slide fades the list out over the top and bottom 6 % of its area (a CSS mask)."""
    from PIL import ImageChops
    mask = scene["fade_mask"]
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    return layer


def render_frames(out_dir: str, W: int, H: int, teams: List[Dict[str, Any]], location: str, date: str,
                  rounds: List[Dict[str, Any]], seconds: int, fps: int = 20) -> int:
    scene = build_scene(W, H, teams, location, date, rounds)
    total = int(seconds * fps)
    for i in range(total):
        frame_at(scene, i / fps, seconds).save(os.path.join(out_dir, f"frame_{i:05d}.png"), "PNG", compress_level=1)
    return total


def encode_mp4(out_path: str, W: int, H: int, teams: List[Dict[str, Any]], location: str, date: str,
               rounds: List[Dict[str, Any]], seconds: int, fps: int = 20, ffmpeg: str = "ffmpeg") -> Tuple[bool, str]:
    """Draw the frames and pipe them straight into ffmpeg (no frame files on disk, no PNG compression). Returns (ok, error text)."""
    import subprocess
    scene = build_scene(W, H, teams, location, date, rounds)
    total = int(seconds * fps)
    cmd = [ffmpeg, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-framerate", str(fps), "-i", "-",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "21", "-r", str(fps), "-movflags", "+faststart", out_path]
    kw: Dict[str, Any] = {}
    if sys.platform == "win32":
        kw["creationflags"] = 0x08000000                       # no console window flash
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **kw)
    err = b""
    try:
        for i in range(total):
            proc.stdin.write(frame_at(scene, i / fps, seconds).tobytes())
        proc.stdin.close()
        err = proc.stderr.read()
        rc = proc.wait(timeout=300)
    except (BrokenPipeError, OSError) as e:                    # ffmpeg died early: its own message is the useful one
        try:
            err = proc.stderr.read()
        except Exception:                                      # noqa: BLE001
            pass
        proc.kill()
        return False, (err.decode("utf-8", "replace")[-300:] or str(e))
    if rc != 0:
        return False, err.decode("utf-8", "replace")[-300:]
    return True, ""
