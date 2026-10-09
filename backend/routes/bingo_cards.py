"""alpha.109: Bingo card generator routes. Cards come ONLY from the song lists found in the user's Bingo folder
(the same folder + switches as Bingo Setup). No presets, no SharePoint."""
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from native import bingo_library as bl
from native import bingo_cards as bc

router = APIRouter(prefix="/cards", tags=["bingo-cards"])


class GenerateBody(BaseModel):
    theme: str
    count: int = 40


@router.get("/themes")
async def card_themes():
    """Every Bingo theme found in the user's folder that has a song list, with its song count."""
    s = bl.load_settings()
    themes = bl.card_themes()
    for t in themes:
        t["usable"] = t["songs"] >= t["need"]          # 24 songs for a word card, 16 pictures for a Loteria card
    return {"success": True, "folder": s.get("main_folder") or "", "min_songs": bc.MIN_SONGS, "min_pictures": bc.LOTERIA_PICS,
            "max_cards": bc.MAX_CARDS, "themes": themes}


@router.post("/generate")
async def generate(body: GenerateBody):
    """A PDF of bingo cards (4 per page) built from the chosen theme's song list."""
    allowed = {t["id"] for t in bl.card_themes()}
    if body.theme not in allowed:
        raise HTTPException(status_code=404, detail="theme_not_found")
    try:
        if bc.is_loteria(body.theme):
            # alpha.110: a Loteria round makes PICTURE cards from the theme's "Cards" folder (4 x 4, no free space)
            cf = bl.cards_folder(body.theme)
            if cf is None:
                raise HTTPException(status_code=422, detail="no_cards_folder")
            out = bc.generate_loteria_pdf(cf, body.count, body.theme)
        else:
            res = bl.theme_songs(body.theme)
            if res is None or res.get("error"):
                raise HTTPException(status_code=404, detail=(res or {}).get("error") or "theme_not_found")
            out = bc.generate_pdf(res["songs"], body.count, body.theme)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    name = re.sub(r'[^A-Za-z0-9 _().-]+', "", body.theme).strip() or "Bingo"
    return Response(content=out["pdf"], media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="Bingo Cards - %s (%d cards).pdf"' % (name, out["cards"]),
        "X-Cards": str(out["cards"]), "X-Pages": str(out["pages"]), "X-Songs": str(out["songs_used"]),
        "Access-Control-Expose-Headers": "X-Cards, X-Pages, X-Songs, Content-Disposition"})
