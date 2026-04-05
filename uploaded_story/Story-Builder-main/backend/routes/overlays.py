"""
Overlay Routes - API endpoints for overlay management
"""
from fastapi import APIRouter, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Dict, Optional
from pydantic import BaseModel
import logging

from overlay_service import OverlayService

router = APIRouter(prefix="/overlays", tags=["overlays"])
logger = logging.getLogger(__name__)

# Database will be injected
db: AsyncIOMotorDatabase = None


def set_database(database):
    global db
    db = database


class ApplyOverlaysRequest(BaseModel):
    """Request to apply overlays to a presentation"""
    presentationId: str
    locationName: str
    slides: Optional[List[Dict]] = None  # Optional: pass slides directly if already loaded


class PreviewOverlaysRequest(BaseModel):
    """Request to preview overlays for a presentation"""
    presentationId: str
    locationName: str
    slides: Optional[List[Dict]] = None  # Optional: pass slides directly


class ApplySectionOverlaysRequest(BaseModel):
    """Request to apply overlays to a single section's slides"""
    locationName: str
    slides: List[Dict]
    roundNumber: Optional[int] = None
    roundType: Optional[str] = None


@router.get("/metadata/{location_name}")
async def get_overlay_metadata(location_name: str) -> Dict:
    """
    Get overlay metadata for a location WITHOUT downloading images.
    Returns lightweight metadata that frontend uses to request individual images.
    This avoids the huge 34MB response that was timing out.
    """
    try:
        overlay_service = OverlayService()
        
        # Get overlays for this location (just metadata, no downloads)
        overlays = overlay_service.get_location_overlays(location_name)
        
        if not overlays:
            return {
                'success': True,
                'location': location_name,
                'overlays': [],
                'message': f'No overlays available for {location_name}'
            }
        
        # Return only metadata - no base64 data
        overlay_metadata = []
        for overlay in overlays:
            overlay_metadata.append({
                'name': overlay['name'],
                'roundNumber': overlay.get('roundNumber'),
                'type': overlay['type'],
                'path': overlay['path'],
                'size': overlay.get('size', 0)
            })
        
        logger.info(f"✅ Returning metadata for {len(overlay_metadata)} overlays for {location_name}")
        
        return {
            'success': True,
            'location': location_name,
            'overlays': overlay_metadata
        }
        
    except Exception as e:
        logger.error(f"Error getting overlay metadata: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'overlays': []
        }


@router.get("/image")
async def get_single_overlay_image(path: str) -> Dict:
    """
    Get a single overlay image as base64 data URL.
    This endpoint is called individually for each overlay to avoid huge payloads.
    Uses server-side caching for fast repeated requests.
    """
    try:
        overlay_service = OverlayService()
        
        # Determine type from path extension
        overlay_type = 'gif' if path.lower().endswith('.gif') else 'png'
        
        # Get the overlay as base64 data URL (uses caching)
        data_url = overlay_service.get_overlay_as_data_url(path, overlay_type)
        
        if not data_url:
            return {
                'success': False,
                'error': f'Failed to load overlay: {path}'
            }
        
        logger.info(f"✅ Returning single overlay image: {path.split('/')[-1]}")
        
        return {
            'success': True,
            'dataUrl': data_url
        }
        
    except Exception as e:
        logger.error(f"Error getting overlay image: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


@router.get("/images/{location_name}")
async def get_overlay_images(location_name: str) -> Dict:
    """
    DEPRECATED: Get all overlay images for a location as base64 data URLs.
    WARNING: This can return 30-40MB of data and may timeout in production.
    Use /metadata/{location_name} + /image?path=... instead for lazy loading.
    """
    try:
        overlay_service = OverlayService()
        
        # Get overlays for this location
        overlays = overlay_service.get_location_overlays(location_name)
        
        if not overlays:
            return {
                'success': True,
                'location': location_name,
                'overlays': [],
                'message': f'No overlays available for {location_name}'
            }
        
        # Download each overlay and convert to base64
        overlay_images = []
        for overlay in overlays:
            data_url = overlay_service.get_overlay_as_data_url(overlay['path'], overlay['type'])
            if data_url:
                overlay_images.append({
                    'name': overlay['name'],
                    'roundNumber': overlay.get('roundNumber'),
                    'type': overlay['type'],
                    'dataUrl': data_url
                })
        
        logger.info(f"✅ Returning {len(overlay_images)} overlay images for {location_name}")
        
        return {
            'success': True,
            'location': location_name,
            'overlays': overlay_images
        }
        
    except Exception as e:
        logger.error(f"Error getting overlay images: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'overlays': []
        }


@router.post("/apply-section")
async def apply_section_overlays(request: ApplySectionOverlaysRequest) -> Dict:
    """
    Apply overlays to a single section's slides.
    Faster than full presentation overlay - designed for progressive loading.
    """
    try:
        overlay_service = OverlayService()
        
        # Get overlays for this location
        overlays = overlay_service.get_location_overlays(request.locationName)
        
        if not overlays:
            return {
                'success': True,
                'overlaysApplied': 0,
                'slides': request.slides,
                'message': f'No overlays available for {request.locationName}'
            }
        
        slides = request.slides
        applied_count = 0
        
        # Pre-load all overlay images into cache to avoid repeated downloads
        logger.info(f"📥 Pre-loading {len(overlays)} overlay images...")
        for overlay in overlays:
            overlay_service.get_overlay_as_data_url(overlay['path'], overlay['type'])
        logger.info(f"✅ All overlays pre-loaded")
        
        # Find round title slide and apply overlays based on round rules
        for i, slide in enumerate(slides):
            if not slide:
                continue
            
            metadata = slide.get('metadata') or {}
            
            # Check if this is a round title slide
            if metadata.get('isRoundTitle'):
                round_number = metadata.get('roundNumber') or request.roundNumber
                round_type = metadata.get('roundType') or request.roundType
                
                if round_number and round_type:
                    # Find overlays for this round
                    round_overlay = overlay_service.find_overlay_for_round(overlays, round_number, round_type)
                    answer_overlay = overlay_service.find_overlay_by_name(overlays, "Answers")
                    
                    # Get overlay applications based on round rules
                    applications = overlay_service.get_overlay_applications(
                        round_type, i, round_overlay, answer_overlay
                    )
                    
                    # Apply overlays
                    for app in applications:
                        slide_idx = app['slideIndex']
                        overlay_to_apply = app['overlay']
                        
                        if 0 <= slide_idx < len(slides) and overlay_to_apply:
                            slides[slide_idx] = overlay_service.apply_overlay_to_slide(
                                slides[slide_idx], overlay_to_apply
                            )
                            applied_count += 1
                    
                    break  # Only one round title per section
        
        logger.info(f"✅ Section overlay complete: {applied_count} overlays applied")
        
        return {
            'success': True,
            'overlaysApplied': applied_count,
            'slides': slides
        }
        
    except Exception as e:
        logger.error(f"Error applying section overlays: {str(e)}")
        return {
            'success': False,
            'overlaysApplied': 0,
            'slides': request.slides,
            'error': str(e)
        }


@router.get("/location/{location_name}")
async def get_location_overlays(location_name: str) -> List[Dict]:
    """
    Get all available overlays for a specific location
    
    Args:
        location_name: Name of the location (e.g., "Chicago")
        
    Returns:
        List of overlay files with metadata
    """
    try:
        overlay_service = OverlayService()
        overlays = overlay_service.get_location_overlays(location_name)
        
        return overlays
    
    except Exception as e:
        logger.error(f"Error fetching overlays for location {location_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preview/{presentation_id}")
async def preview_overlays(
    presentation_id: str,
    location_name: str
) -> Dict:
    """
    Preview which overlays will be applied to a presentation
    
    Args:
        presentation_id: ID of the presentation
        location_name: Location name for overlay lookup
        
    Returns:
        Preview information about overlays
    """
    try:
        # Get presentation from database
        presentation = await db.presentations.find_one({'id': presentation_id})
        
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")
        
        overlay_service = OverlayService()
        
        # Get all available overlays for this location
        overlays = overlay_service.get_location_overlays(location_name)
        
        # Load slides - handle different presentation types
        slides = []
        if presentation.get('type') == 'trivia-imported':
            # For trivia-imported, load slides from SharePoint cache via trivia-import service
            from routes import trivia_import
            from gridfs_service import get_gridfs_service
            try:
                slides_response = await trivia_import.get_imported_slides(presentation_id)
                
                # Handle chunked response - need to load all chunks
                if slides_response and slides_response.get('chunked') and slides_response.get('totalChunks', 0) > 0:
                    logger.info(f"📦 Chunked presentation detected, loading {slides_response['totalChunks']} chunks...")
                    gridfs = get_gridfs_service()
                    slides = await gridfs.get_all_slides(presentation_id)
                    if slides:
                        logger.info(f"📦 Loaded {len(slides)} slides from GridFS")
                    else:
                        logger.warning("⚠️ Failed to load slides from GridFS")
                        slides = []
                elif slides_response and 'slides' in slides_response:
                    slides = slides_response['slides']
                    logger.info(f"📦 Loaded {len(slides)} slides from trivia-import service")
            except Exception as e:
                logger.error(f"Failed to load slides via trivia-import: {str(e)}")
                slides = []
        else:
            slides = presentation.get('slides', [])
        
        preview_data = []
        
        # Process each slide to find round titles
        for i, slide in enumerate(slides):
            # Skip if slide is None or not a dict
            if not slide or not isinstance(slide, dict):
                logger.warning(f"⚠️ Skipping invalid slide at index {i} in preview")
                continue
            
            # Handle None metadata - use 'or {}' to ensure we get empty dict if metadata is None
            slide_metadata = slide.get('metadata') or {}
            
            # Only process round title slides (slide 1 of each round)
            if not slide_metadata.get('isRoundTitle'):
                continue
            
            round_number = slide_metadata.get('roundNumber')
            round_type = slide_metadata.get('roundType')
            
            if not round_number or not round_type:
                continue
            
            # Find appropriate overlay for this round
            overlay = overlay_service.find_overlay_for_round(
                overlays,
                round_number,
                round_type
            )
            
            # Get slide title from first text element
            slide_title = "Unknown"
            text_elements = [el for el in slide.get('elements', []) if el.get('type') == 'text']
            if text_elements:
                slide_title = text_elements[0].get('content', 'Unknown')[:50]
            
            preview_data.append({
                'slideIndex': i,
                'slideTitle': slide_title,
                'roundNumber': round_number,
                'roundType': round_type,
                'overlayName': overlay['name'] if overlay else None,
                'overlayPath': overlay['path'] if overlay else None,
                'willApplyToSlide': i + 1 if overlay and i + 1 < len(slides) else None
            })
        
        return {
            'totalSlides': len(slides),
            'availableOverlays': len(overlays),
            'preview': preview_data
        }
    
    except Exception as e:
        logger.error(f"Error generating overlay preview: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview-with-slides/{presentation_id}")
async def preview_overlays_with_slides(
    presentation_id: str,
    request: PreviewOverlaysRequest
) -> Dict:
    """
    Preview overlays with slides passed directly in request body.
    Use this when slides are already loaded in the frontend.
    """
    try:
        overlay_service = OverlayService()
        
        # Get all available overlays for this location
        overlays = overlay_service.get_location_overlays(request.locationName)
        
        # Use slides from request
        slides = request.slides or []
        
        if not slides:
            return {
                'totalSlides': 0,
                'availableOverlays': len(overlays),
                'preview': [],
                'error': 'No slides provided'
            }
        
        preview_data = []
        
        # Process each slide to find round titles
        for i, slide in enumerate(slides):
            if not slide or not isinstance(slide, dict):
                continue
            
            slide_metadata = slide.get('metadata') or {}
            
            # Only process round title slides
            if not slide_metadata.get('isRoundTitle'):
                continue
            
            round_number = slide_metadata.get('roundNumber')
            round_type = slide_metadata.get('roundType')
            
            if not round_number or not round_type:
                continue
            
            # Find appropriate overlay for this round
            overlay = overlay_service.find_overlay_for_round(
                overlays,
                round_type,
                round_number
            )
            
            preview_data.append({
                'slideIndex': i,
                'roundNumber': round_number,
                'roundType': round_type,
                'overlayName': overlay['name'] if overlay else None,
                'overlayPath': overlay['path'] if overlay else None,
                'willApplyToSlide': i + 1 if overlay and i + 1 < len(slides) else None
            })
        
        return {
            'totalSlides': len(slides),
            'availableOverlays': len(overlays),
            'preview': preview_data
        }
    
    except Exception as e:
        logger.error(f"Error generating overlay preview: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply/{presentation_id}")
async def apply_overlays_to_presentation(
    presentation_id: str,
    request: ApplyOverlaysRequest
) -> Dict:
    """
    Apply overlays to a presentation based on slide metadata
    
    This endpoint:
    1. Fetches the presentation from MongoDB
    2. Gets available overlays for the specified location
    3. Reads metadata from each slide to determine round info
    4. Applies appropriate overlay to slides
    5. Updates presentation in MongoDB
    
    Args:
        presentation_id: ID of the presentation
        request: Contains location name for overlay lookup
        
    Returns:
        Summary of applied overlays
    """
    try:
        # Get presentation from database
        presentation = await db.presentations.find_one({'id': presentation_id})
        
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")
        
        overlay_service = OverlayService()
        
        # Get all available overlays for this location
        overlays = overlay_service.get_location_overlays(request.locationName)
        
        if not overlays:
            raise HTTPException(
                status_code=404,
                detail=f"No overlays found for location: {request.locationName}"
            )
        
        logger.info(f"🎨 Applying overlays to presentation: {presentation['name']}")
        logger.info(f"📍 Location: {request.locationName}")
        logger.info(f"🎭 Available overlays: {len(overlays)}")
        
        # Track applied overlays
        applied_count = 0
        skipped_count = 0
        applied_details = []
        
        # Load slides - handle different presentation types
        slides = []
        update_via_sharepoint = False
        
        # PRIORITY 1: Use slides passed directly in request (most reliable)
        if request.slides and len(request.slides) > 0:
            slides = request.slides
            update_via_sharepoint = True
            logger.info(f"📦 Using {len(slides)} slides passed in request")
        elif presentation.get('type') == 'trivia-imported':
            # For trivia-imported, load slides from SharePoint cache via trivia-import service
            from routes import trivia_import
            from gridfs_service import get_gridfs_service
            try:
                slides_response = await trivia_import.get_imported_slides(presentation_id)
                
                # Handle chunked response - need to load all chunks
                if slides_response and slides_response.get('chunked') and slides_response.get('totalChunks', 0) > 0:
                    logger.info(f"📦 Chunked presentation detected, loading {slides_response['totalChunks']} chunks...")
                    gridfs = get_gridfs_service()
                    slides = await gridfs.get_all_slides(presentation_id)
                    if slides:
                        update_via_sharepoint = True
                        logger.info(f"📦 Loaded {len(slides)} slides from GridFS")
                    else:
                        logger.warning("⚠️ No slides in GridFS - cannot apply overlays")
                        return {
                            'success': False,
                            'overlaysApplied': 0,
                            'overlaysSkipped': 0,
                            'details': [],
                            'totalSlides': 0,
                            'slides': [],
                            'error': 'No slides found. Please reload the presentation first.'
                        }
                elif slides_response and 'slides' in slides_response:
                    slides = slides_response['slides']
                    update_via_sharepoint = True
                    logger.info(f"📦 Loaded {len(slides)} slides from trivia-import service")
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to load slides via trivia-import: {str(e)}")
                return {
                    'success': False,
                    'overlaysApplied': 0,
                    'error': f'Failed to load slides: {str(e)}'
                }
        else:
            slides = presentation.get('slides', [])
            logger.info(f"📦 Loaded {len(slides)} slides from presentations collection")
        
        # Process each slide to find round titles
        for i, slide in enumerate(slides):
            # Skip if slide is None or not a dict
            if not slide or not isinstance(slide, dict):
                logger.warning(f"⚠️ Skipping invalid slide at index {i}")
                continue
            
            # Handle None metadata - use 'or {}' to ensure we get empty dict if metadata is None
            slide_metadata = slide.get('metadata') or {}
            
            # Only process round title slides (slide 1 of each round)
            if not slide_metadata.get('isRoundTitle'):
                continue
            
            round_number = slide_metadata.get('roundNumber')
            round_type = slide_metadata.get('roundType')
            
            if not round_number or not round_type:
                continue
            
            logger.info(f"📄 Slide {i}: Found Round {round_number} Title ({round_type})")
            
            # Find all overlays for this round
            round_overlay = overlay_service.find_overlay_for_round(overlays, round_number, round_type)
            answer_overlay = overlay_service.find_overlay_by_name(overlays, "Answers")
            
            # Apply overlays based on round type and rules
            overlay_applications = overlay_service.get_overlay_applications(
                round_type, i, round_overlay, answer_overlay
            )
            
            for app in overlay_applications:
                slide_idx = app['slideIndex']
                overlay_to_apply = app['overlay']
                
                if slide_idx < len(slides) and overlay_to_apply:
                    slides[slide_idx] = overlay_service.apply_overlay_to_slide(
                        slides[slide_idx],
                        overlay_to_apply
                    )
                    applied_count += 1
                    
                    applied_details.append({
                        'slideIndex': slide_idx,
                        'roundNumber': round_number,
                        'roundType': round_type,
                        'overlayName': overlay_to_apply['name'],
                        'overlayPath': overlay_to_apply['path']
                    })
                    
                    logger.info(f"✅ Applied {overlay_to_apply['name']} to slide {slide_idx + 1}")
            
            if not round_overlay:
                skipped_count += 1
                logger.warning(f"⚠️ No round overlay found for Round {round_number} ({round_type})")
        
        # Apply sponsor overlay to second-to-last slide of SPONSOR section
        logger.info("🎯 Looking for sponsor overlay (99_Sponsor) and sponsor section...")
        sponsor_overlay = overlay_service.find_overlay_by_name(overlays, "99_Sponsor")
        
        if sponsor_overlay:
            # Find all slides in the sponsor section
            sponsor_slide_indices = []
            for i, slide in enumerate(slides):
                if slide and isinstance(slide, dict):
                    slide_metadata = slide.get('metadata') or {}
                    if slide_metadata.get('roundType') == 'SPONSOR':
                        sponsor_slide_indices.append(i)
            
            if len(sponsor_slide_indices) >= 2:
                # Apply to second-to-last slide of sponsor section
                second_to_last_sponsor_idx = sponsor_slide_indices[-2]
                slides[second_to_last_sponsor_idx] = overlay_service.apply_overlay_to_slide(
                    slides[second_to_last_sponsor_idx],
                    sponsor_overlay
                )
                applied_count += 1
                
                applied_details.append({
                    'slideIndex': second_to_last_sponsor_idx,
                    'roundNumber': 99,
                    'roundType': 'SPONSOR',
                    'overlayName': sponsor_overlay['name'],
                    'overlayPath': sponsor_overlay['path']
                })
                
                logger.info(f"✅ Applied sponsor overlay {sponsor_overlay['name']} to slide {second_to_last_sponsor_idx + 1} (second-to-last of sponsor section with {len(sponsor_slide_indices)} slides)")
            elif len(sponsor_slide_indices) == 1:
                # If only one sponsor slide, apply to it
                sponsor_idx = sponsor_slide_indices[0]
                slides[sponsor_idx] = overlay_service.apply_overlay_to_slide(
                    slides[sponsor_idx],
                    sponsor_overlay
                )
                applied_count += 1
                
                applied_details.append({
                    'slideIndex': sponsor_idx,
                    'roundNumber': 99,
                    'roundType': 'SPONSOR',
                    'overlayName': sponsor_overlay['name'],
                    'overlayPath': sponsor_overlay['path']
                })
                
                logger.info(f"✅ Applied sponsor overlay {sponsor_overlay['name']} to slide {sponsor_idx + 1} (only sponsor slide)")
            else:
                logger.warning("⚠️ No sponsor section found in presentation")
        else:
            logger.warning("⚠️ No 99_Sponsor overlay found in location folder")
        
        # Update presentation - save back to SharePoint cache for trivia-imported
        if update_via_sharepoint:
            # Save updated slides back to SharePoint cache (00_Built folder)
            try:
                from sharepoint_service import SharePointService
                from gridfs_service import get_gridfs_service
                import json
                import tempfile
                
                sp = SharePointService()
                trivia_pres = await db.trivia_presentations.find_one({'id': presentation_id})
                
                if trivia_pres:
                    # Get location path for cache path
                    location_path = trivia_pres.get('location', '')
                    
                    # Build cache path
                    cache_folder = f"{location_path}/00_Built"
                    cache_file = f"{cache_folder}/{presentation_id}.json"
                    
                    # Prepare updated data
                    built_data = {
                        "id": presentation_id,
                        "slides": slides,
                        "lastModified": trivia_pres.get('createdAt').isoformat() if trivia_pres.get('createdAt') else None,
                        "totalSlides": len(slides)
                    }
                    
                    # Save to temp file then upload
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
                        json.dump(built_data, tmp, default=str)
                        tmp_path = tmp.name
                    
                    try:
                        sp.upload_file(tmp_path, cache_file)
                        logger.info(f"💾 Updated slides in SharePoint cache: {cache_file}")
                    finally:
                        import os
                        os.unlink(tmp_path)
                    
                    # Also update GridFS cache so next load has overlays
                    try:
                        gridfs = get_gridfs_service()
                        
                        # Verify slides have overlays before saving
                        overlay_count = sum(1 for s in slides if any(e.get('zIndex') == 1000 for e in s.get('elements', [])))
                        logger.info(f"📊 Saving to GridFS: {len(slides)} slides, {overlay_count} with overlays")
                        
                        await gridfs.store_slides(
                            presentation_id,
                            slides,
                            metadata={
                                'location': location_path,
                                'name': trivia_pres.get('name', ''),
                                'overlays_applied': True,
                                'overlay_count': overlay_count
                            }
                        )
                        logger.info("💾 Updated slides in GridFS cache")
                    except Exception as gridfs_err:
                        logger.warning(f"⚠️ Could not update GridFS cache: {str(gridfs_err)}")
                        
            except Exception as e:
                logger.error(f"Error updating SharePoint cache: {str(e)}")
                # Don't fail the entire operation if cache update fails
        else:
            # Regular presentation - update in database
            await db.presentations.update_one(
                {'id': presentation_id},
                {'$set': {'slides': slides}}
            )
            logger.info("💾 Updated slides in presentations collection")
        
        logger.info(f"🎉 Overlay application complete: {applied_count} applied, {skipped_count} skipped")
        
        # Only return slides if overlays were applied (and only the modified ones to reduce payload)
        response_data = {
            'success': True,
            'overlaysApplied': applied_count,
            'overlaysSkipped': skipped_count,
            'details': applied_details[:20],  # Limit details for response size
            'totalSlides': len(slides)
        }
        
        # Return slides only if overlays were applied
        if applied_count > 0:
            response_data['slides'] = slides
        
        return response_data
        
    except Exception as e:
        logger.error(f"Error applying overlays: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
