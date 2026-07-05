"""
Slide Fetcher - Fetches and processes slides section by section on-demand.
Each section is fetched, compressed, stored, and marked complete.
Called by frontend when user opens a presentation.

Uses HYBRID converter (Rust + Python) for 10-20x faster parsing.

OPTIMIZATION: Resource limits to prevent memory exhaustion
"""
from fastapi import APIRouter, HTTPException, Request, Body
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
import tempfile
import os
import shutil
import gc
from datetime import datetime
from typing import Optional, List, Dict, Any

from sharepoint_service import SharePointService
from hybrid_pptx_converter import get_hybrid_converter, RUST_AVAILABLE
from gridfs_service import get_gridfs_service
# v32.0.0-alpha.46: DISK-FIRST native slide renderer. See PRD § "DISK STATE
# IS THE ABSOLUTE SOURCE OF TRUTH". This module builds Editor-compatible
# slides directly from the `.bighat` files on disk, so the Presenter is
# not gated on SharePoint availability.
from native_slides import (
    native_render_section as _native_render_section,
    load_presentation_from_disk as _load_pres_from_disk,
)

router = APIRouter(prefix="/slide-fetcher", tags=["slide-fetcher"])
logger = logging.getLogger(__name__)

# OPTIMIZATION: Resource limits
MAX_SLIDES_PER_SECTION = 50  # Prevent loading too many slides at once
MAX_CONCURRENT_FETCHES = 3   # Limit concurrent section fetches

# Track active fetches for resource management
_active_fetches = 0

# Log whether Rust is available
if RUST_AVAILABLE:
    logger.info("🦀 Rust PPTX parser is available - using hybrid mode for faster parsing")
else:
    logger.warning("⚠️ Rust PPTX parser not available - using Python-only mode")

db: AsyncIOMotorDatabase = None

def set_database(database):
    global db
    db = database


@router.post("/fetch-section/{presentation_id}/{section_name}")
async def fetch_section(presentation_id: str, section_name: str, request: Request = None):
    """
    Fetch a single section of slides from SharePoint.
    Called by frontend one section at a time.
    Returns the slides for that section.
    """
    global _active_fetches
    
    # OPTIMIZATION: Limit concurrent fetches to prevent resource exhaustion
    if _active_fetches >= MAX_CONCURRENT_FETCHES:
        raise HTTPException(
            status_code=503, 
            detail=f"Server busy - {_active_fetches} fetches in progress. Please retry."
        )
    
    _active_fetches += 1
    
    try:
        # Parse request body if present (may contain round metadata)
        body = {}
        try:
            if request:
                body = await request.json()
        except Exception:
            pass
        
        # v32.0.0-alpha.46: DISK IS TRUTH. Try DB first for speed, but fall
        # back to `Files/Trivia/Rounds/*.bighat` on disk if the DB doesn't
        # have this presentation. A fresh MontyDB (post-restart) will miss
        # every previous session's work — the disk manifest is what
        # actually lives across launches.
        trivia_pres = None
        try:
            trivia_pres = await db.trivia_presentations.find_one(
                {"id": presentation_id},
                {"_id": 0}
            )
        except Exception as db_exc:
            logger.warning("[slide-fetcher] DB lookup failed, falling to disk: %s", db_exc)
        if not trivia_pres:
            trivia_pres = _load_pres_from_disk(presentation_id)
        
        if not trivia_pres:
            raise HTTPException(status_code=404, detail="Presentation not found")

        # v32.0.0-alpha.46: NATIVE DISK RENDER PATH.
        # For the desktop native build there is no SharePoint. Render the
        # section directly from `.bighat` data. If the render returns
        # slides, we return them and skip the SharePoint/PPTX pipeline
        # entirely. This is what fixes the "Package not found at
        # C:\Users\...\Temp\fetch_host_XXXX\file_0.pptx" 500 the merchant
        # saw on alpha.45.
        try:
            native_slides = _native_render_section(trivia_pres, section_name, body)
        except Exception as native_exc:
            logger.exception("[slide-fetcher] native render failed: %s", native_exc)
            native_slides = []
        if native_slides:
            # Mark section complete in DB best-effort (nice-to-have index).
            try:
                await db.section_status.update_one(
                    {"presentationId": presentation_id, "section": section_name},
                    {"$set": {
                        "status": "complete",
                        "slidesCount": len(native_slides),
                        "completedAt": datetime.utcnow(),
                        "source": "native-disk",
                    }},
                    upsert=True,
                )
            except Exception:
                pass
            logger.info(
                "[slide-fetcher] native render %s → %d slides (disk-first)",
                section_name, len(native_slides),
            )
            return {
                "section": section_name,
                "slides": native_slides,
                "slidesCount": len(native_slides),
                "status": "complete",
                "source": "native-disk",
            }

        # Fall through to SharePoint/PPTX pipeline (legacy cloud mode).
        sp = SharePointService()
        # Use hybrid converter (Rust + Python) for faster parsing
        converter = get_hybrid_converter()
        temp_dir = tempfile.mkdtemp(prefix=f"fetch_{section_name}_")
        
        slides = []
        
        try:
            logger.info(f"📦 Fetching section '{section_name}' for {presentation_id}")
            
            if section_name == "host":
                # Fetch host slides
                host_file = trivia_pres.get('hostFile', '')
                if host_file:
                    slides = await _fetch_pptx_slides(sp, converter, temp_dir, host_file, 0)
                    logger.info(f"  ✓ Host: {len(slides)} slides")
            
            elif section_name == "location":
                # Fetch location slides
                location_file = trivia_pres.get('locationFile', '')
                if location_file:
                    logger.info(f"  📍 Location file: {location_file}")
                    slides = await _fetch_pptx_slides(sp, converter, temp_dir, location_file, 0)
                    logger.info(f"  ✓ Location: {len(slides)} slides")
                else:
                    logger.warning(f"  ⚠️ No location file defined for presentation {presentation_id}")
            
            elif section_name.startswith("round_"):
                # Fetch round slides
                round_num = int(section_name.split("_")[1])
                round_files = trivia_pres.get('roundFiles', [])
                round_type = body.get('roundType', '')  # From request body
                round_file_path = None
                
                # Strategy 1: Look in roundFiles array
                for rf in round_files:
                    if rf.get('order') == round_num:
                        round_type = rf.get('type', round_type)
                        round_file_path = rf.get('file', '')
                        break
                
                # Strategy 2: Derive round file path from location folder structure
                if not round_file_path:
                    location = trivia_pres.get('location', '')
                    num_rounds = trivia_pres.get('numRounds', 3)
                    
                    # Determine round type based on position if not provided
                    if not round_type:
                        if num_rounds == 3:
                            round_type = ['REG', 'MISC', 'BIG'][round_num - 1] if round_num <= 3 else 'UNKNOWN'
                        elif num_rounds == 5:
                            round_type = ['MC', 'REG', 'MISC', 'MYS', 'BIG'][round_num - 1] if round_num <= 5 else 'UNKNOWN'
                        elif num_rounds == 6:
                            round_type = ['MC', 'REG', 'REG', 'MISC', 'MYS', 'BIG'][round_num - 1] if round_num <= 6 else 'UNKNOWN'
                    
                    # Derive file path from location and round type
                    if location:
                        # Use location directly - it's already the location folder path
                        location_folder = location
                        
                        # Map round types to folder names
                        round_folder_map = {
                            'MC': '01_MC',
                            'REG': '02_REG',
                            'MISC': '03_MISC',
                            'MYS': '04_MYS',
                            'BIG': '05_BIG'
                        }
                        
                        round_folder = round_folder_map.get(round_type, f'{round_num:02d}_{round_type}')
                        
                        # Standard location for round files in "Live Stream Show"
                        if 'Live Stream Show' in location:
                            # Live Stream Show rounds are in the Rounds folder
                            round_file_path = f"01_Trivia/Web App/00_Builder/01_Rounds/{round_folder}"
                        else:
                            # Try location-specific rounds folder
                            round_file_path = f"{location_folder}/Rounds/{round_folder}"
                        
                        logger.info(f"  Derived round path: {round_file_path}")
                
                if round_file_path:
                    slides = await _fetch_pptx_slides(
                        sp, converter, temp_dir, round_file_path, 0,
                        round_type=round_type, round_order=round_num
                    )
                    
                    # VALIDATION: Check that slides have expected text content
                    if slides and round_type == 'BIG':
                        # BIG round validation: critical slides must have text
                        critical_indices = [1, 3, 4, 5, 6]
                        missing_text_slides = []
                        
                        for idx in critical_indices:
                            if idx < len(slides):
                                slide = slides[idx]
                                slide_elements = slide.get('elements', []) if isinstance(slide, dict) else (slide.elements if hasattr(slide, 'elements') else [])
                                text_elements = [e for e in slide_elements if (e.get('type') if isinstance(e, dict) else getattr(e, 'type', None)) == 'text']
                                # Also check for empty-content text elements
                                real_text = [e for e in text_elements if (e.get('content') if isinstance(e, dict) else getattr(e, 'content', '')) and str(e.get('content') if isinstance(e, dict) else getattr(e, 'content', '')).strip()]
                                if not real_text:
                                    missing_text_slides.append(idx)
                        
                        if missing_text_slides:
                            logger.warning(f"  ⚠️ BIG round slides {missing_text_slides} missing text — retrying with Python fallback")
                            # Re-fetch the entire BIG round with Python to recover text
                            try:
                                retry_slides = await _fetch_pptx_slides(
                                    sp, converter, temp_dir, round_file_path, 0,
                                    round_type=round_type, round_order=round_num
                                )
                                if retry_slides:
                                    # Replace only the slides that had missing text
                                    for idx in missing_text_slides:
                                        if idx < len(retry_slides):
                                            retry_slide = retry_slides[idx]
                                            retry_texts = [e for e in (retry_slide.get('elements', []) if isinstance(retry_slide, dict) else []) if (e.get('type') if isinstance(e, dict) else '') == 'text']
                                            if retry_texts:
                                                slides[idx] = retry_slide
                                                logger.info(f"  ✅ BIG slide {idx}: Recovered {len(retry_texts)} text elements on retry")
                            except Exception as retry_err:
                                logger.error(f"  ❌ BIG retry failed: {retry_err}")
                        else:
                            logger.info("  ✓ BIG round validation passed: all critical slides have text")
                    
                    elif slides and round_type in ['MC', 'REG', 'MISC', 'MYS']:
                        # Question round validation: slides 1-10 (or 1-9 for MYS) should have text
                        max_q = 9 if round_type == 'MYS' else 10
                        missing_text_count = 0
                        
                        for idx in range(1, min(max_q + 1, len(slides))):
                            slide = slides[idx]
                            slide_elements = slide.get('elements', []) if isinstance(slide, dict) else (slide.elements if hasattr(slide, 'elements') else [])
                            text_elements = [e for e in slide_elements if (e.get('type') if isinstance(e, dict) else getattr(e, 'type', None)) == 'text']
                            if not text_elements:
                                missing_text_count += 1
                        
                        if missing_text_count > 0:
                            logger.warning(f"  ⚠️ {round_type} round: {missing_text_count} question slides missing text")
                        else:
                            logger.info(f"  ✓ {round_type} round validation passed: all question slides have text")
                    
                    # Add score slide after non-BIG rounds
                    if round_type in ['MC', 'REG', 'MISC', 'MYS'] and slides:
                        score_slide = {
                            "order": len(slides),
                            "background": "radial-gradient(circle at center, #1657E8 5%, #1F5EE9 20%, #191919 90%)",
                            "elements": [],
                            "metadata": {"isScoreSlide": True, "roundType": round_type, "roundNumber": round_num}
                        }
                        slides.append(score_slide)
                    logger.info(f"  ✓ Round {round_num} ({round_type}): {len(slides)} slides")
                else:
                    logger.warning(f"  ⚠️ No file path found for round {round_num}")
            
            elif section_name == "sponsors":
                # Fetch sponsor slides - use stored sponsors or default master sponsor
                sponsor_files = trivia_pres.get('sponsorFiles', [])
                
                # If no sponsors configured, use the master sponsor file
                if not sponsor_files:
                    sponsor_files = ["01_Trivia/Web App/00_Builder/03_Sponsors/04_Main Sponsors.pptx"]
                    logger.info("  Using default master sponsor file")
                
                for idx, sponsor_path in enumerate(sponsor_files):
                    sponsor_slides = await _fetch_pptx_slides(sp, converter, temp_dir, sponsor_path, len(slides))
                    # Add SPONSOR metadata to each slide for overlay detection
                    for slide_idx, slide in enumerate(sponsor_slides):
                        if isinstance(slide, dict):
                            if slide.get('metadata') is None:
                                slide['metadata'] = {}
                            slide['metadata']['roundType'] = 'SPONSOR'
                            slide['metadata']['slideIndexInRound'] = slide_idx
                        elif hasattr(slide, 'metadata'):
                            if slide.metadata is None:
                                slide.metadata = {}
                            slide.metadata['roundType'] = 'SPONSOR'
                            slide.metadata['slideIndexInRound'] = slide_idx
                    slides.extend(sponsor_slides)
                logger.info(f"  ✓ Sponsors: {len(slides)} slides (with SPONSOR metadata)")
            
            elif section_name == "winners":
                # Fetch winners from shared URL
                winners_url = "https://bhentertainment.sharepoint.com/:p:/g/IQCo2aaE1BlBR7z8IjwBRKROATpgpfl7Dbh5KM-RLwy3z0M?e=ASi38L"
                local_path = os.path.join(temp_dir, "winners.pptx")
                
                if sp.download_file_by_sharing_url(winners_url, local_path):
                    raw_slides = converter.convert_pptx_to_slides(local_path, 0)
                    for idx, slide in enumerate(raw_slides):
                        slide_dict = slide.model_dump()
                        if slide_dict.get('metadata') is None:
                            slide_dict['metadata'] = {}
                        slide_dict['metadata']['roundType'] = 'WINNERS'
                        slide_dict['metadata']['slideIndexInRound'] = idx
                        slides.append(slide_dict)
                logger.info(f"  ✓ Winners: {len(slides)} slides")
            
            elif section_name == "final_scores":
                # Add final scores CSS animation slide
                slides = [{
                    "order": 0,
                    "background": "radial-gradient(circle at center, #1657E8 5%, #1F5EE9 20%, #191919 90%)",
                    "elements": [],
                    "metadata": {
                        "roundType": "WINNERS",
                        "slideIndexInRound": 4,
                        "isFinalScoresSlide": True
                    }
                }]
                logger.info("  ✓ Final Scores: 1 slide")
            
            # Mark section as complete in database
            await db.section_status.update_one(
                {"presentationId": presentation_id, "section": section_name},
                {
                    "$set": {
                        "status": "complete",
                        "slidesCount": len(slides),
                        "completedAt": datetime.utcnow()
                    }
                },
                upsert=True
            )
            
            # VALIDATION: Warn if important sections have no slides
            if len(slides) == 0 and section_name in ['location', 'host']:
                logger.warning(f"  ⚠️ SECTION '{section_name}' returned 0 slides - this may indicate a problem!")
            
            return {
                "section": section_name,
                "slides": slides,
                "slidesCount": len(slides),
                "status": "complete"
            }
            
        finally:
            converter.cleanup()
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching section {section_name}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # OPTIMIZATION: Always decrement active fetches counter
        _active_fetches -= 1
        # Trigger garbage collection after large operations to free memory
        gc.collect()


@router.get("/sections-list/{presentation_id}")
async def get_sections_list(presentation_id: str):
    """Get the list of sections to fetch for a presentation.

    v32.0.0-alpha.46: falls back to `Files/Trivia/Rounds/*.bighat` on disk
    when the presentation isn't in the DB (fresh MontyDB after restart).
    """
    try:
        trivia_pres = None
        try:
            trivia_pres = await db.trivia_presentations.find_one(
                {"id": presentation_id},
                {"_id": 0}
            )
        except Exception as db_exc:
            logger.warning("[sections-list] DB lookup failed: %s", db_exc)
        if not trivia_pres:
            trivia_pres = _load_pres_from_disk(presentation_id)
        
        if not trivia_pres:
            raise HTTPException(status_code=404, detail="Presentation not found")
        
        sections = []
        
        # v32.0.0-alpha.46: include Host if host NAME set (native renders
        # from text — no PPTX required). Same for Location.
        if trivia_pres.get('hostFile') or trivia_pres.get('host') or trivia_pres.get('hostName'):
            sections.append({"name": "host", "type": "host"})
        
        if trivia_pres.get('locationFile') or trivia_pres.get('location'):
            sections.append({"name": "location", "type": "location"})
        
        # Rounds - insert sponsors BEFORE BIG round (always the last round)
        round_files = trivia_pres.get('roundFiles', [])

        # v32.0.0-alpha.48: Enforce canonical round order regardless of how
        # the wizard wrote them: MC → REG → MISC → (extra REG/MISC) → MYS →
        # BIG. MYS is always second-to-last, BIG is always last. Ties
        # within a bucket preserve the wizard's ordering.
        _ROUND_TYPE_RANK = {"MC": 1, "REG": 2, "MISC": 3, "NONSENSE": 3, "MYS": 98, "BIG": 99}
        if round_files:
            round_files = sorted(
                enumerate(round_files),
                key=lambda p: (_ROUND_TYPE_RANK.get((p[1].get("type") or "").upper(), 50), p[0]),
            )
            round_files = [rf for _idx, rf in round_files]
            # Re-index the `order` field to reflect the new sequence so
            # the frontend renders as `round_1, round_2, ...` in the
            # canonical order.
            for i, rf in enumerate(round_files, start=1):
                rf["order"] = i
            trivia_pres["roundFiles"] = round_files

        # Always include sponsors (default master sponsor if none configured)
        num_rounds = trivia_pres.get('numRounds', len(round_files) if round_files else 3)
        sponsors_added = False
        
        if round_files:
            # Use round metadata if available
            for rf in round_files:
                round_type = rf.get('type', '')
                round_order = rf.get('order', 0)
                
                # Insert sponsors before BIG round (or before last round if no type)
                if not sponsors_added:
                    is_big = round_type == 'BIG' or round_order == num_rounds
                    if is_big:
                        sections.append({"name": "sponsors", "type": "sponsors"})
                        sponsors_added = True
                
                sections.append({
                    "name": f"round_{round_order}",
                    "type": "round",
                    "roundType": round_type,
                    "roundOrder": round_order
                })
        else:
            # No round metadata - generate based on numRounds
            # Last round is always BIG, sponsors go before it
            for i in range(1, num_rounds + 1):
                # Insert sponsors before the last round (BIG)
                if not sponsors_added and i == num_rounds:
                    sections.append({"name": "sponsors", "type": "sponsors"})
                    sponsors_added = True
                
                # Determine round type based on position and total rounds
                if num_rounds == 3:
                    round_type = ['REG', 'MISC', 'BIG'][i-1]
                elif num_rounds == 5:
                    round_type = ['MC', 'REG', 'MISC', 'MYS', 'BIG'][i-1]
                elif num_rounds == 6:
                    round_type = ['MC', 'REG', 'REG', 'MISC', 'MYS', 'BIG'][i-1]
                else:
                    round_type = 'BIG' if i == num_rounds else 'UNKNOWN'
                
                sections.append({
                    "name": f"round_{i}",
                    "type": "round",
                    "roundType": round_type,
                    "roundOrder": i
                })
        
        # Fallback: if sponsors weren't added (shouldn't happen), add them before winners
        if not sponsors_added:
            sections.append({"name": "sponsors", "type": "sponsors"})
        
        # Winners
        sections.append({"name": "winners", "type": "winners"})
        
        # Final scores
        sections.append({"name": "final_scores", "type": "final_scores"})
        
        return {
            "presentationId": presentation_id,
            "sections": sections,
            "totalSections": len(sections)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sections list: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/store-all/{presentation_id}")
async def store_all_slides(presentation_id: str, request: Request):
    """Store all slides in GridFS after the frontend has accumulated them.

    v32.0.0-alpha.46: In native mode disk is truth — the DB cache is a
    nice-to-have index, not a requirement. The frontend calls this at
    end-of-load as a fire-and-forget best-effort cache. Accept a raw list
    body (legacy), a `{slides: [...]}` wrapper (new), OR an empty body
    without 422ing so the Editor's `.catch(() => {})` chain stays clean.
    """
    try:
        # Parse the raw body ourselves so we accept: list | {slides: list} | empty.
        slides: List[Any] = []
        try:
            payload = await request.json()
        except Exception:
            payload = None
        if isinstance(payload, list):
            slides = payload
        elif isinstance(payload, dict):
            candidate = payload.get("slides")
            if isinstance(candidate, list):
                slides = candidate

        if not slides:
            logger.info(
                "[slide-fetcher] store-all called with empty payload for %s — "
                "skipping cache write (disk is truth)", presentation_id,
            )
            return {"status": "skipped", "slidesCount": 0, "reason": "empty-body"}

        gridfs = get_gridfs_service()
        
        # Get presentation info for metadata (best-effort)
        trivia_pres = None
        try:
            trivia_pres = await db.trivia_presentations.find_one(
                {"id": presentation_id},
                {"_id": 0, "name": 1, "location": 1}
            )
        except Exception:
            pass
        if not trivia_pres:
            trivia_pres = _load_pres_from_disk(presentation_id) or {}
        
        await gridfs.store_slides(
            presentation_id,
            slides,
            metadata={
                "name": trivia_pres.get("name", ""),
                "location": trivia_pres.get("location", "")
            }
        )
        
        logger.info(f"✅ Stored {len(slides)} slides in GridFS for {presentation_id}")
        
        return {
            "status": "complete",
            "slidesCount": len(slides)
        }
    
    except Exception as e:
        logger.error(f"Error storing slides: {str(e)}")
        # v32.0.0-alpha.46: never 500 on store-all. Disk is truth; the DB
        # cache is optional. Return a soft-fail so the Editor keeps going.
        return {"status": "error", "slidesCount": 0, "error": str(e)}


async def _fetch_pptx_slides(sp, converter, temp_dir, file_path, start_order, round_type=None, round_order=None):
    """Helper to fetch and convert a PPTX file to slides"""
    slides = []
    local_path = os.path.join(temp_dir, f"file_{start_order}.pptx")
    
    download_success = False
    if file_path.startswith('sharepoint://'):
        drive_id, item_id = sp.parse_sharepoint_path(file_path)
        if drive_id and item_id:
            download_success = sp.download_file_by_item_id(drive_id, item_id, local_path)
    else:
        download_success = sp.download_file(file_path, local_path)
    
    if download_success:
        raw_slides = converter.convert_pptx_to_slides(local_path, start_order, round_type, round_order)
        for slide in raw_slides:
            slides.append(slide.model_dump())
    
    return slides
