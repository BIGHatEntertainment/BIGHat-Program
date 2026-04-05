"""Round Generator Routes - PPTX generation for trivia rounds"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
import os
import json
import logging
import traceback
from datetime import datetime, timezone

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.dml.color import RGBColor

router = APIRouter(prefix="/roundmaker", tags=["roundmaker"])
logger = logging.getLogger(__name__)

db: AsyncIOMotorDatabase = None

BACKEND_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BACKEND_DIR / "roundmaker_uploads"
GENERATED_DIR = BACKEND_DIR / "roundmaker_generated"
ASSETS_DIR = BACKEND_DIR / "roundmaker_assets"
UPLOAD_DIR.mkdir(exist_ok=True)
GENERATED_DIR.mkdir(exist_ok=True)

def set_database(database):
    global db
    db = database

class QuestionItem(BaseModel):
    number: int
    question: str
    answer: str
    options: Optional[List[str]] = None
    correctOption: Optional[int] = None

class TiebreakerItem(BaseModel):
    question: str
    answer: str

class RoundCreate(BaseModel):
    round_type: str
    name: str
    questions: List[QuestionItem]
    tiebreaker: Optional[TiebreakerItem] = None
    cover_image_id: Optional[str] = None

class RoundResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    round_type: str
    name: str
    questions: List[dict]
    tiebreaker: Optional[dict] = None
    cover_image_id: Optional[str] = None
    status: str
    created_at: str
    pptx_path: Optional[str] = None

# ── Upload Cover Image ──

@router.post("/upload-cover")
async def upload_cover(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix or ".png"
    file_path = UPLOAD_DIR / f"{file_id}{ext}"
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    return {"file_id": file_id, "filename": file.filename, "path": str(file_path)}

# ── Serve uploaded images ──

@router.get("/uploads/{filename}")
async def serve_upload(filename: str):
    """Serve uploaded/downloaded images for preview."""
    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path))

# ── Round CRUD ──

@router.post("/rounds", response_model=RoundResponse)
async def create_round(data: RoundCreate):
    round_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": round_id,
        "round_type": data.round_type,
        "name": data.name,
        "questions": [q.model_dump() for q in data.questions],
        "tiebreaker": data.tiebreaker.model_dump() if data.tiebreaker else None,
        "cover_image_id": data.cover_image_id,
        "status": "draft",
        "created_at": now,
        "pptx_path": None,
    }
    await db.rounds.insert_one(doc)
    doc.pop("_id", None)
    return RoundResponse(**doc)

@router.get("/rounds", response_model=List[RoundResponse])
async def list_rounds():
    rounds = await db.rounds.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [RoundResponse(**r) for r in rounds]

@router.get("/rounds/{round_id}", response_model=RoundResponse)
async def get_round(round_id: str):
    doc = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Round not found")
    return RoundResponse(**doc)

@router.delete("/rounds/{round_id}")
async def delete_round(round_id: str):
    result = await db.rounds.delete_one({"id": round_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Round not found")
    return {"status": "deleted"}

@router.post("/rounds/{round_id}/duplicate", response_model=RoundResponse)
async def duplicate_round(round_id: str):
    """Duplicate an existing round as a new draft with '(Copy)' suffix."""
    original = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not original:
        raise HTTPException(status_code=404, detail="Round not found")

    new_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": new_id,
        "round_type": original["round_type"],
        "name": f"{original['name']} (Copy)",
        "questions": original.get("questions", []),
        "tiebreaker": original.get("tiebreaker"),
        "cover_image_id": original.get("cover_image_id"),
        "status": "draft",
        "created_at": now,
        "pptx_path": None,
    }
    await db.rounds.insert_one(doc)
    doc.pop("_id", None)
    return RoundResponse(**doc)

# ── PowerPoint Generation ──

ASSETS_DIR = BACKEND_DIR / "roundmaker_assets"

def _add_text_slide(prs, text, font_size=32, bold=False, color=RGBColor(0xFF, 0xFF, 0xFF), bg_color=RGBColor(0x0F, 0x16, 0x29)):
    """Add a slide with centered text on dark background."""
    slide_layout = prs.slide_layouts[6]  # Blank
    slide = prs.slides.add_slide(slide_layout)
    # Set background
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = bg_color

    width = prs.slide_width
    height = prs.slide_height
    txBox = slide.shapes.add_textbox(Emu(0), Emu(int(height * 0.3)), width, Emu(int(height * 0.4)))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.bold = bold
    p.font.color.rgb = color
    p.alignment = PP_ALIGN.CENTER
    return slide

def _add_question_slide(prs, number, question, options=None, round_type=None):
    """Add a question slide. For MC, no 'Question X' title, just question text + A/B/C/D options."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = RGBColor(0x0F, 0x16, 0x29)

    width = prs.slide_width
    height = prs.slide_height

    if round_type == "MC":
        # MC: No question number title, question text starts higher
        txBox2 = slide.shapes.add_textbox(Emu(int(width * 0.05)), Emu(int(height * 0.15)), Emu(int(width * 0.9)), Emu(int(height * 0.3)))
        tf2 = txBox2.text_frame
        tf2.word_wrap = True
        p2 = tf2.paragraphs[0]
        p2.text = question
        p2.font.size = Pt(28)
        p2.font.bold = True
        p2.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p2.alignment = PP_ALIGN.CENTER

        # MC options
        if options:
            labels = ["A", "B", "C", "D"]
            y_start = int(height * 0.50)
            for i, opt in enumerate(options[:4]):
                txOpt = slide.shapes.add_textbox(
                    Emu(int(width * 0.15)),
                    Emu(y_start + i * int(height * 0.11)),
                    Emu(int(width * 0.7)),
                    Emu(int(height * 0.09))
                )
                tfOpt = txOpt.text_frame
                tfOpt.word_wrap = True
                pOpt = tfOpt.paragraphs[0]
                pOpt.text = f"{labels[i]}) {opt}"
                pOpt.font.size = Pt(22)
                pOpt.font.color.rgb = RGBColor(0x2D, 0xD4, 0xBF)
                pOpt.alignment = PP_ALIGN.LEFT
    else:
        # Non-MC: Keep question number title
        txBox = slide.shapes.add_textbox(Emu(int(width * 0.05)), Emu(int(height * 0.08)), Emu(int(width * 0.9)), Emu(int(height * 0.12)))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = f"Question {number}"
        p.font.size = Pt(24)
        p.font.bold = True
        p.font.color.rgb = RGBColor(0xFA, 0xCC, 0x15)
        p.alignment = PP_ALIGN.CENTER

        txBox2 = slide.shapes.add_textbox(Emu(int(width * 0.05)), Emu(int(height * 0.25)), Emu(int(width * 0.9)), Emu(int(height * 0.3)))
        tf2 = txBox2.text_frame
        tf2.word_wrap = True
        p2 = tf2.paragraphs[0]
        p2.text = question
        p2.font.size = Pt(28)
        p2.font.bold = True
        p2.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p2.alignment = PP_ALIGN.CENTER

    return slide

def _get_review_title(round_type, round_name=""):
    """Get the review slide title based on round type.
    MC -> 'Multiple Choice', REG/MISC/MYS -> category name without _N suffix."""
    if round_type == "MC":
        return "Multiple Choice"
    import re
    # Strip trailing _N suffix: "1980s_4" -> "1980s", "Sports_5" -> "Sports"
    clean = re.sub(r'_\d+$', '', round_name) if round_name else ""
    return clean or "Review"

def _add_review_slide(prs, questions, round_type, round_name=""):
    """Add a review slide listing all questions."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = RGBColor(0x0F, 0x16, 0x29)

    width = prs.slide_width
    height = prs.slide_height

    # Title - MC says "Multiple Choice", others say category name
    review_title = _get_review_title(round_type, round_name)
    txBox = slide.shapes.add_textbox(Emu(int(width * 0.05)), Emu(int(height * 0.03)), Emu(int(width * 0.9)), Emu(int(height * 0.1)))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = review_title
    p.font.size = Pt(28)
    p.font.bold = True
    p.font.color.rgb = RGBColor(0xFA, 0xCC, 0x15)
    p.alignment = PP_ALIGN.CENTER

    # Questions list
    num_q = len(questions)
    font_size = 14 if num_q > 8 else 18
    y_start = int(height * 0.14)
    available = int(height * 0.82)
    line_h = available // max(num_q, 1)

    for i, q in enumerate(questions):
        txQ = slide.shapes.add_textbox(
            Emu(int(width * 0.05)),
            Emu(y_start + i * line_h),
            Emu(int(width * 0.9)),
            Emu(line_h)
        )
        tfQ = txQ.text_frame
        tfQ.word_wrap = True
        pQ = tfQ.paragraphs[0]
        pQ.text = f"{i+1}. {q['question']}"
        pQ.font.size = Pt(font_size)
        pQ.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        pQ.alignment = PP_ALIGN.LEFT

    return slide

def _add_answers_slide(prs, questions, round_type):
    """Add answers slide with all answers listed vertically. MC has no title."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = RGBColor(0x0F, 0x16, 0x29)

    width = prs.slide_width
    height = prs.slide_height

    if round_type != "MC":
        # Non-MC: Show "Answers" title
        txBox = slide.shapes.add_textbox(Emu(int(width * 0.05)), Emu(int(height * 0.03)), Emu(int(width * 0.9)), Emu(int(height * 0.1)))
        tf = txBox.text_frame
        p = tf.paragraphs[0]
        p.text = "Answers"
        p.font.size = Pt(28)
        p.font.bold = True
        p.font.color.rgb = RGBColor(0xFA, 0xCC, 0x15)
        p.alignment = PP_ALIGN.CENTER

    num_q = len(questions)
    font_size = 14 if num_q > 8 else 18
    y_start = int(height * 0.05) if round_type == "MC" else int(height * 0.14)
    available = int(height * 0.90) if round_type == "MC" else int(height * 0.82)
    line_h = available // max(num_q, 1)

    for i, q in enumerate(questions):
        answer_text = f"{i+1}. {q.get('answer', '')}"

        txA = slide.shapes.add_textbox(
            Emu(int(width * 0.08)),
            Emu(y_start + i * line_h),
            Emu(int(width * 0.84)),
            Emu(line_h)
        )
        tfA = txA.text_frame
        tfA.word_wrap = True
        pA = tfA.paragraphs[0]
        pA.text = answer_text
        pA.font.size = Pt(font_size)
        pA.font.color.rgb = RGBColor(0x2D, 0xD4, 0xBF)
        pA.alignment = PP_ALIGN.LEFT if round_type == "MC" else PP_ALIGN.CENTER

    return slide

def _add_cover_slide(prs, cover_path):
    """Add cover image slide. Image fills entire 16:9 slide."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = RGBColor(0x0F, 0x16, 0x29)

    if cover_path and Path(cover_path).exists():
        width = prs.slide_width
        height = prs.slide_height
        # Fill the entire slide (16:9 landscape)
        slide.shapes.add_picture(str(cover_path), Emu(0), Emu(0), width, height)
    return slide

def _add_gif_slide(prs):
    """Add the GIF slide with the BIG Hat Trivia image filling the slide."""
    gif_path = ASSETS_DIR / "times_up.gif"
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = RGBColor(0x0F, 0x16, 0x29)

    if gif_path.exists():
        width = prs.slide_width
        height = prs.slide_height
        # Fill the entire slide
        slide.shapes.add_picture(str(gif_path), Emu(0), Emu(0), width, height)
    return slide

def _find_cover_image(file_id):
    """Find uploaded cover image by file_id."""
    if not file_id:
        return None
    for f in UPLOAD_DIR.iterdir():
        if f.stem == file_id:
            return str(f)
    return None

def generate_pptx(round_data):
    """Generate a PowerPoint presentation for the given round."""
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    round_type = round_data["round_type"]
    round_name = round_data.get("name", "")
    questions = round_data["questions"]
    cover_path = _find_cover_image(round_data.get("cover_image_id"))

    # Slide 1: Cover image
    if round_type == "MC":
        mc_title = ASSETS_DIR / "mc_title.jpg"
        _add_cover_slide(prs, str(mc_title) if mc_title.exists() else None)
    else:
        _add_cover_slide(prs, cover_path)

    if round_type == "MC":
        for q in questions[:10]:
            opts = q.get("options")
            _add_question_slide(prs, q["number"], q["question"], options=opts, round_type="MC")
        _add_review_slide(prs, questions[:10], round_type, round_name)
        _add_gif_slide(prs)
        _add_answers_slide(prs, questions[:10], round_type)

    elif round_type in ("REG", "MISC"):
        for q in questions[:10]:
            _add_question_slide(prs, q["number"], q["question"], round_type=round_type)
        _add_review_slide(prs, questions[:10], round_type, round_name)
        _add_gif_slide(prs)
        _add_answers_slide(prs, questions[:10], round_type)

    elif round_type == "MYS":
        for q in questions[:9]:
            _add_question_slide(prs, q["number"], q["question"], round_type=round_type)
        _add_review_slide(prs, questions[:10], round_type, round_name)
        _add_gif_slide(prs)
        _add_answers_slide(prs, questions[:10], round_type)

    elif round_type == "BIG":
        tiebreaker = round_data.get("tiebreaker") or {}
        # Slide 2: The question
        _add_question_slide(prs, 1, questions[0]["question"] if questions else "")
        # Slide 3: GIF
        _add_gif_slide(prs)
        # Slide 4: Question again (review)
        _add_text_slide(prs, questions[0]["question"] if questions else "", font_size=28, bold=True)
        # Slide 5: Answers
        _add_answers_slide(prs, questions, round_type)
        # Slide 6: Tiebreaker question
        _add_text_slide(prs, f"Tiebreaker: {tiebreaker.get('question', '')}", font_size=28, bold=True, color=RGBColor(0xFA, 0xCC, 0x15))
        # Slide 7: Tiebreaker Q + Answer
        slide_layout = prs.slide_layouts[6]
        slide = prs.slides.add_slide(slide_layout)
        bg_fill = slide.background.fill
        bg_fill.solid()
        bg_fill.fore_color.rgb = RGBColor(0x0F, 0x16, 0x29)
        w = prs.slide_width
        h = prs.slide_height
        txBox = slide.shapes.add_textbox(Emu(int(w * 0.1)), Emu(int(h * 0.2)), Emu(int(w * 0.8)), Emu(int(h * 0.25)))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = tiebreaker.get("question", "")
        p.font.size = Pt(24)
        p.font.bold = True
        p.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        p.alignment = PP_ALIGN.CENTER
        txBox2 = slide.shapes.add_textbox(Emu(int(w * 0.1)), Emu(int(h * 0.55)), Emu(int(w * 0.8)), Emu(int(h * 0.2)))
        tf2 = txBox2.text_frame
        tf2.word_wrap = True
        p2 = tf2.paragraphs[0]
        p2.text = tiebreaker.get("answer", "")
        p2.font.size = Pt(28)
        p2.font.bold = True
        p2.font.color.rgb = RGBColor(0x2D, 0xD4, 0xBF)
        p2.alignment = PP_ALIGN.CENTER

    output_path = GENERATED_DIR / f"{round_data['name'].replace(' ', '_')}.pptx"
    prs.save(str(output_path))
    return str(output_path)


@router.post("/rounds/{round_id}/generate")
async def generate_round_pptx(round_id: str):
    doc = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Round not found")

    try:
        pptx_path = generate_pptx(doc)
        await db.rounds.update_one(
            {"id": round_id},
            {"$set": {"pptx_path": pptx_path, "status": "generated"}}
        )
        return FileResponse(
            pptx_path,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=f"{doc['name']}.pptx"
        )
    except Exception as e:
        logger.error(f"PPTX generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── SharePoint Integration ──

try:
    from sharepoint_service import upload_round_to_sharepoint, get_access_token, SHAREPOINT_SHARE_LINKS, list_reg_title_images, download_reg_title_image, list_sharepoint_folder_files
    HAS_SHAREPOINT = True
except ImportError:
    HAS_SHAREPOINT = False
    logger.warning("Round Maker SharePoint functions not available - using local storage only")
    def upload_round_to_sharepoint(*args, **kwargs): return {"success": False, "message": "SharePoint not configured"}
    def get_access_token(): return None
    SHAREPOINT_SHARE_LINKS = {}
    def list_reg_title_images(): return []
    def download_reg_title_image(*args, **kwargs): return None
    def list_sharepoint_folder_files(*args, **kwargs): return []

# ── REG Title Images ──

# Cache for title images list (avoid hitting SharePoint on every request)
_reg_images_cache = {"data": None, "expires": 0}
_reg_files_cache = {"data": None, "expires": 0}

@router.get("/reg-title-images")
async def get_reg_title_images():
    """List available title images from the REG SharePoint folder.
    Returns image names to use as round category dropdown options."""
    import time
    now = time.time()
    if _reg_images_cache["data"] and now < _reg_images_cache["expires"]:
        return {"images": _reg_images_cache["data"]}

    try:
        images = await list_reg_title_images()
        _reg_images_cache["data"] = images
        _reg_images_cache["expires"] = now + 300  # Cache for 5 minutes
        return {"images": images}
    except Exception as e:
        logger.error(f"Failed to list REG title images: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/reg-next-number/{category}")
async def get_reg_next_number(category: str):
    """Get the next available number for a REG round category.
    Checks the actual SharePoint REG output folder for existing .pptx files
    with the naming convention {Category}_{N}.pptx to find the highest number.
    """
    import re
    import time

    now = time.time()
    # Cache the SharePoint file list for 2 minutes
    if not _reg_files_cache["data"] or now >= _reg_files_cache["expires"]:
        try:
            files = await list_sharepoint_folder_files(SHAREPOINT_SHARE_LINKS["REG"])
            _reg_files_cache["data"] = files
            _reg_files_cache["expires"] = now + 120
        except Exception as e:
            logger.error(f"Failed to list REG folder: {e}")
            _reg_files_cache["data"] = []

    sp_files = _reg_files_cache["data"] or []

    # Parse filenames: "1980s_3.pptx" -> category="1980s", number=3
    max_num = 0
    escaped_cat = re.escape(category)
    pattern = re.compile(rf'^{escaped_cat}_(\d+)\.pptx$', re.IGNORECASE)

    for filename in sp_files:
        match = pattern.match(filename)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num

    next_num = max_num + 1
    round_name = f"{category}_{next_num}"
    logger.info(f"REG next number for '{category}': {next_num} (found max {max_num} on SharePoint)")
    return {"category": category, "next_number": next_num, "round_name": round_name, "existing_count": max_num}

@router.post("/reg-download-title-image")
async def download_title_image_endpoint(item_id: str, drive_id: str, filename: str):
    """Download a title image from SharePoint and save it locally for PPTX generation."""
    try:
        save_dir = str(UPLOAD_DIR)
        local_path = await download_reg_title_image(item_id, drive_id, filename, save_dir)
        # Return a file_id that can be used as cover_image_id
        file_id = Path(local_path).stem
        return {"file_id": file_id, "path": local_path, "filename": filename}
    except Exception as e:
        logger.error(f"Failed to download title image: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── MC Naming Convention ──
# MC follows: MC_01_A, MC_02_A, ... MC_20_A, MC_01_B, MC_02_B, ... MC_20_B, etc.
# Every 20 iterations starts a new letter.

_mc_files_cache = {"data": None, "expires": 0}

@router.get("/mc-next-name")
async def get_mc_next_name():
    """Get the next available MC round name.
    Scans SharePoint MC folder for files matching MC_NN_X.pptx pattern.
    Returns the next name in sequence: MC_01_A -> MC_20_A -> MC_01_B -> etc.
    """
    import re
    import time

    now = time.time()
    if not _mc_files_cache["data"] or now >= _mc_files_cache["expires"]:
        try:
            files = await list_sharepoint_folder_files(SHAREPOINT_SHARE_LINKS["MC"])
            _mc_files_cache["data"] = files
            _mc_files_cache["expires"] = now + 120
        except Exception as e:
            logger.error(f"Failed to list MC folder: {e}")
            _mc_files_cache["data"] = []

    sp_files = _mc_files_cache["data"] or []

    # Parse MC_NN_X.pptx -> track which (number, letter) pairs exist
    pattern = re.compile(r'^MC_(\d+)_([A-Z])\.pptx$', re.IGNORECASE)
    existing = set()
    for filename in sp_files:
        match = pattern.match(filename)
        if match:
            num = int(match.group(1))
            letter = match.group(2).upper()
            existing.add((num, letter))

    # Find the next available slot
    # Walk through letters A, B, C... and for each letter check numbers 1-20
    letters = [chr(i) for i in range(ord('A'), ord('Z') + 1)]

    # Find the highest letter that has any entries
    next_num = 1
    next_letter = 'A'
    found = False

    for letter in letters:
        nums_for_letter = [n for (n, lt) in existing if lt == letter]
        if nums_for_letter:
            max_num = max(nums_for_letter)
            if max_num < 20:
                # This letter still has room
                next_num = max_num + 1
                next_letter = letter
                found = True
                break
            # This letter is full (20), continue to next letter
        else:
            if found is False:
                # Check if previous letters exist
                prev_idx = letters.index(letter) - 1
                if prev_idx >= 0:
                    prev_letter = letters[prev_idx]
                    prev_nums = [n for (n, lt) in existing if lt == prev_letter]
                    if prev_nums and max(prev_nums) == 20:
                        # Previous letter is full, start this letter
                        next_num = 1
                        next_letter = letter
                        found = True
                        break
                    elif not prev_nums and letter == 'A':
                        # No entries at all, start fresh
                        next_num = 1
                        next_letter = 'A'
                        found = True
                        break
                else:
                    # Letter A with no entries
                    next_num = 1
                    next_letter = 'A'
                    found = True
                    break

    if not found:
        # Fallback: start from A_1
        next_num = 1
        next_letter = 'A'

    round_name = f"MC_{next_num:02d}_{next_letter}"
    existing_count = len(existing)
    logger.info(f"MC next name: {round_name} (found {existing_count} existing MC files)")
    return {
        "round_name": round_name,
        "next_number": next_num,
        "next_letter": next_letter,
        "existing_count": existing_count,
    }

@router.get("/sharepoint-status")
async def sharepoint_status():
    """Check if SharePoint credentials are configured and test the connection."""
    tenant_id = os.environ.get("AZURE_TENANT_ID")
    client_id = os.environ.get("AZURE_CLIENT_ID")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET")
    configured = all([tenant_id, client_id, client_secret])
    
    # Test token acquisition if configured
    token_valid = False
    error_msg = None
    if configured:
        try:
            await get_access_token()
            token_valid = True
        except Exception as e:
            error_msg = str(e)
    
    return {
        "configured": configured,
        "token_valid": token_valid,
        "error": error_msg,
        "folders": {k: v.split("?")[0] for k, v in SHAREPOINT_SHARE_LINKS.items()},
    }


@router.post("/rounds/{round_id}/upload-sharepoint")
async def upload_to_sharepoint(round_id: str):
    """Generate PPTX and upload to the correct SharePoint folder based on round type."""
    doc = await db.rounds.find_one({"id": round_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Round not found")

    try:
        # Generate the PPTX first
        pptx_path = generate_pptx(doc)
        filename = f"{doc['name']}.pptx"
        
        # Upload to SharePoint
        result = await upload_round_to_sharepoint(
            round_type=doc["round_type"],
            filename=filename,
            file_path=pptx_path,
        )
        
        # Update round status in DB
        await db.rounds.update_one(
            {"id": round_id},
            {"$set": {
                "status": "uploaded",
                "pptx_path": pptx_path,
                "sharepoint_url": result.get("web_url"),
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        
        return {
            "status": "success",
            "message": f"Uploaded to SharePoint ({result.get('folder', doc['round_type'])} folder)",
            "web_url": result.get("web_url"),
            "file_id": result.get("file_id"),
        }
    except Exception as e:
        logger.error(f"SharePoint upload error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Health ──

@router.get("/")
async def root():
    return {"message": "BIG Hat Presenter - Trivia Round Creator API"}

# Include router

