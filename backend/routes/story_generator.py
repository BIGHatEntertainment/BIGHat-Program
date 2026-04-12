"""
Story Generator Routes - API endpoints for generating Instagram story videos.

Uses async job queue to avoid Cloudflare timeout (520 errors).

OPTIMIZATION: Resource limits for video generation
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from typing import List, Dict, Optional
import logging
import os
import re
import uuid
import gc
import tempfile
import base64
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

from story_generator_service import get_story_service

router = APIRouter(prefix="/story-generator", tags=["story-generator"])
logger = logging.getLogger(__name__)

db: AsyncIOMotorDatabase = None

# In-memory job store for video generation status
# Format: {job_id: {status, progress, error, result, created_at, updated_at}}
video_jobs: Dict[str, Dict] = {}

# OPTIMIZATION: Limit max concurrent video jobs and total stored jobs
MAX_CONCURRENT_JOBS = 2
MAX_STORED_JOBS = 10

# Thread pool for CPU-bound video encoding - limited workers
video_executor = ThreadPoolExecutor(max_workers=1)  # Reduced from 2 to 1

def set_database(database):
    global db
    db = database

def _cleanup_old_jobs():
    """Remove old completed jobs to prevent memory buildup"""
    global video_jobs
    if len(video_jobs) > MAX_STORED_JOBS:
        # Sort by created_at and remove oldest completed jobs
        completed = [
            (jid, job) for jid, job in video_jobs.items() 
            if job.get('status') in ['completed', 'failed']
        ]
        completed.sort(key=lambda x: x[1].get('created_at', ''))
        
        # Remove oldest jobs beyond limit
        for jid, _ in completed[:len(video_jobs) - MAX_STORED_JOBS]:
            del video_jobs[jid]
            logger.info(f"🧹 Cleaned up old job: {jid}")
        
        gc.collect()

@router.get("/presentations")
async def list_presentations_for_story(userName: Optional[str] = None) -> List[Dict]:
    """
    List all trivia presentations available for story generation.
    Optionally filter by user.
    """
    try:
        query = {}
        if userName:
            query['createdBy'] = userName.lower()
        
        presentations = await db.trivia_presentations.find(query).sort('createdAt', -1).to_list(100)
        
        result = []
        for p in presentations:
            # Use stored round names and types if available (new format)
            round_names = p.get('roundNames', [])
            round_types = p.get('roundTypes', [])
            num_rounds = p.get('numRounds') or len(p.get('roundFiles', []))
            
            # Build rounds info - prefer stored data over runtime resolution
            rounds_info = []
            if round_names and round_types:
                # Use stored round data (new format - reliable)
                for idx, (name, rtype) in enumerate(zip(round_names, round_types)):
                    # For MC and MYS, override with fixed names
                    if rtype == 'MC':
                        display_name = 'Multiple Choice'
                    elif rtype == 'MYS':
                        display_name = 'Mystery'
                    else:
                        display_name = name
                    
                    rounds_info.append({
                        'order': idx + 1,
                        'type': rtype,
                        'name': display_name
                    })
            else:
                # Fallback to old format - try to resolve from roundFiles
                service = get_story_service()
                round_files = p.get('roundFiles', [])
                for rf in round_files:
                    round_type = rf.get('type', 'REG')
                    round_file = rf.get('file', '')
                    
                    # For MC and MYS, use fixed names
                    if round_type == 'MC':
                        round_name = 'Multiple Choice'
                    elif round_type == 'MYS':
                        round_name = 'Mystery'
                    else:
                        # For REG, MISC, and BIG - resolve the actual round name from SharePoint
                        round_name = service.resolve_round_name(round_file)
                        if round_name == 'Unknown' or not round_name:
                            round_name = rf.get('name', f'{round_type} Round')
                    
                    rounds_info.append({
                        'order': rf.get('order', 0),
                        'type': round_type,
                        'name': round_name
                    })
            
            # Get location info - prefer new stored fields
            location_name = p.get('location', '')
            location_folder = p.get('locationFolder', '')
            
            # Fallback for old format where location was full path
            if not location_folder and '/' in location_name:
                location_folder = location_name.split('/')[-1]
                # Clean location name (remove prefix)
                import re
                location_name = re.sub(r'^\d+_', '', location_folder)
            elif not location_folder:
                location_folder = location_name  # Use location as folder name
            
            # Get host name - prefer new stored field
            host_name = p.get('host', '')
            if not host_name:
                # Fallback to extracting from path
                host_path = p.get('hostFile', '')
                host_name = host_path.split('/')[-1].replace('.pptx', '') if host_path else 'Unknown'
            
            result.append({
                'id': p['id'],
                'name': p['name'],
                'createdBy': p.get('createdBy', ''),
                'createdAt': p.get('createdAt'),
                'location': location_name,
                'locationFolder': location_folder,  # Full folder name for SharePoint matching
                'host': host_name,
                'hostPath': p.get('hostFile', ''),
                'numRounds': num_rounds,
                'roundNames': round_names,  # Original round names
                'roundTypes': round_types,  # Round types array
                'rounds': rounds_info,  # Processed rounds with display names
                'totalSlides': p.get('totalSlides', 0)
            })
        
        return result
    
    except Exception as e:
        logger.error(f"Error listing presentations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/presentation/{presentation_id}")
async def get_presentation_details(presentation_id: str) -> Dict:
    """
    Get detailed information about a presentation for story generation preview.
    """
    try:
        presentation = await db.trivia_presentations.find_one({'id': presentation_id})
        if not presentation:
            presentation = await db.presentations.find_one({'id': presentation_id})
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")
        
        # Get the service for resolving round names
        service = get_story_service()
        
        # Extract round info with resolved names
        round_files = presentation.get('roundFiles', [])
        rounds_info = []
        for rf in round_files:
            round_type = rf.get('type', 'REG')
            round_file = rf.get('file', '')
            
            # For MC and MYS, use fixed names
            if round_type == 'MC':
                round_name = 'Multiple Choice'
            elif round_type == 'MYS':
                round_name = 'Mystery'
            else:
                # For REG, MISC, and BIG - resolve the actual round name from SharePoint
                round_name = service.resolve_round_name(round_file)
                if round_name == 'Unknown' or not round_name:
                    round_name = rf.get('name', f'{round_type} Round')
            
            rounds_info.append({
                'order': rf.get('order', 0),
                'type': round_type,
                'name': round_name,
                'file': round_file
            })
        
        # Get location name
        location_path = presentation.get('location', '')
        location_name = location_path.split('/')[-1] if location_path else 'Unknown'
        import re
        location_name = re.sub(r'^\d+_', '', location_name)
        
        # Get host name
        host_path = presentation.get('hostFile', '')
        host_name = host_path.split('/')[-1].replace('.pptx', '') if host_path else 'Unknown'
        
        return {
            'id': presentation['id'],
            'name': presentation['name'],
            'createdBy': presentation.get('createdBy', ''),
            'createdAt': presentation.get('createdAt'),
            'location': location_name,
            'locationPath': location_path,
            'host': host_name,
            'hostPath': host_path,
            'numRounds': len(rounds_info),
            'rounds': rounds_info,
            'totalSlides': presentation.get('totalSlides', 0),
            # Include raw data for story generation
            'rawData': {
                'location': location_path,
                'hostFile': host_path,
                'roundFiles': round_files
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting presentation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/assets")
async def get_available_assets(refresh: bool = False) -> Dict:
    """
    Get list of available assets (location images, host GIFs, backgrounds).
    
    Args:
        refresh: If true, clears the SharePoint cache and fetches fresh data
    """
    try:
        service = get_story_service()
        if refresh:
            service.refresh_sharepoint_cache()
        assets = service.get_available_assets()
        
        # No hints needed if assets are loaded
        assets['missing_asset_hints'] = []
        return assets
    
    except Exception as e:
        logger.error(f"Error getting assets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/refresh-assets")
async def refresh_assets_cache() -> Dict:
    """
    Clear the SharePoint asset cache and reload assets.
    Call this when new locations, hosts, or backgrounds are added to SharePoint.
    """
    try:
        service = get_story_service()
        service.refresh_sharepoint_cache()
        assets = service.get_available_assets()
        return {
            'success': True,
            'message': 'Asset cache refreshed successfully',
            'counts': {
                'locations': len(assets.get('locations', [])),
                'hosts': len(assets.get('hosts', [])),
                'backgrounds': len(assets.get('backgrounds', []))
            },
            'sharepoint_enabled': assets.get('sharepoint_enabled', False)
        }
    except Exception as e:
        logger.error(f"Error refreshing assets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/asset-urls/{presentation_id}")
async def get_asset_urls_for_client(presentation_id: str) -> Dict:
    """
    Get actual asset URLs for client-side video generation.
    Returns base64-encoded images for location, host, and background.
    """
    import base64
    
    try:
        presentation = await db.trivia_presentations.find_one({'id': presentation_id})
        if not presentation:
            presentation = await db.presentations.find_one({'id': presentation_id})
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")
        
        service = get_story_service()
        
        # Get location, host, and round info
        location_path = presentation.get('location', '')
        host_path = presentation.get('hostFile', '')
        round_files = presentation.get('roundFiles', [])
        num_rounds = len(round_files)
        
        # Normalize names
        location_name = service._normalize_location_name(location_path)
        host_name = service._normalize_host_name(host_path)
        
        logger.info(f"[AssetURLs] Getting assets for presentation: {presentation['name']}")
        logger.info(f"[AssetURLs] Location: {location_name}, Host: {host_name}, Rounds: {num_rounds}")
        
        # Get images and convert to base64 data URLs
        assets = {}
        
        # Location image
        location_img = service._get_location_image(location_name)
        if location_img:
            location_img = location_img.convert('RGB')
            location_img = service._resize_to_story(location_img)
            import io
            buffer = io.BytesIO()
            location_img.save(buffer, format='PNG')
            assets['locationUrl'] = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
            logger.info("[AssetURLs] Location image loaded")
        else:
            assets['locationUrl'] = None
            assets['locationMissing'] = True
            logger.warning(f"[AssetURLs] Location image not found: {location_name}")
        
        # Host image
        host_img, _ = service._get_host_image(host_name)
        if host_img:
            host_img = host_img.convert('RGB')
            host_img = service._resize_to_story(host_img)
            import io
            buffer = io.BytesIO()
            host_img.save(buffer, format='PNG')
            assets['hostUrl'] = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
            logger.info("[AssetURLs] Host image loaded")
        else:
            assets['hostUrl'] = None
            assets['hostMissing'] = True
            logger.warning(f"[AssetURLs] Host image not found: {host_name}")
        
        # Background image
        bg_img = service._get_background_image(location_name, num_rounds=num_rounds)
        if bg_img:
            bg_img = bg_img.convert('RGB')
            bg_img = service._resize_to_story(bg_img)
            import io
            buffer = io.BytesIO()
            bg_img.save(buffer, format='PNG')
            assets['backgroundUrl'] = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
            logger.info("[AssetURLs] Background image loaded")
        else:
            assets['backgroundUrl'] = None
            assets['backgroundMissing'] = True
            logger.warning(f"[AssetURLs] Background image not found: {location_name}")
        
        # Also return rounds info with resolved names
        rounds = []
        for rf in round_files:
            round_type = rf.get('type', 'REG')
            round_file = rf.get('file', '')
            
            if round_type == 'MC':
                round_name = 'Multiple Choice'
            elif round_type == 'MYS':
                round_name = 'Mystery'
            else:
                round_name = service.resolve_round_name(round_file)
                if round_name == 'Unknown' or not round_name:
                    round_name = rf.get('name', f'{round_type} Round')
            
            rounds.append({
                'order': rf.get('order', 0),
                'type': round_type,
                'name': round_name
            })
        
        return {
            'success': True,
            'assets': assets,
            'rounds': rounds,
            'numRounds': num_rounds,
            'location': location_name,
            'host': host_name
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting asset URLs: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

class BuildAssetRequest(BaseModel):
    """Request schema for getting assets from build data"""
    location: str
    locationFolder: str
    host: str
    numRounds: int

@router.post("/build-asset-urls")
async def get_build_asset_urls(request: BuildAssetRequest) -> Dict:
    """
    Get asset URLs for client-side video generation using build data.
    This is used by the new Story Generator that reads builds from SharePoint.
    
    Returns base64-encoded images for location, host, and background.
    """
    import base64
    import re
    
    try:
        service = get_story_service()
        
        # Normalize names for asset lookup
        # Location name should be cleaned (no prefix)
        location_name = request.location.lower().replace(' ', '_')
        
        # Also try with the folder name (which may have a prefix)
        location_folder_clean = re.sub(r'^\d+_', '', request.locationFolder).lower().replace(' ', '_')
        
        # Host name should be cleaned
        host_name = request.host.lower().replace(' ', '_')
        
        num_rounds = request.numRounds
        
        logger.info("[BuildAssetURLs] Getting assets for build")
        logger.info(f"[BuildAssetURLs] Location: {location_name}, Host: {host_name}, Rounds: {num_rounds}")
        
        # Get images and convert to base64 data URLs
        assets = {}
        
        # Location image - try multiple name variations
        location_variations = [location_name, location_folder_clean]
        location_variations.extend([v.replace('_', ' ') for v in [location_name, location_folder_clean]])
        location_variations.extend([request.location.lower(), request.locationFolder.lower()])
        # Also try with the prefix intact
        location_variations.append(request.locationFolder.lower().replace(' ', '_'))
        location_variations = list(dict.fromkeys(v for v in location_variations if v))
        
        location_img = None
        for var in location_variations:
            location_img = service._get_location_image(var)
            if location_img:
                break
        
        if location_img:
            location_img = location_img.convert('RGB')
            location_img = service._resize_to_story(location_img)
            import io
            buffer = io.BytesIO()
            location_img.save(buffer, format='PNG')
            assets['locationUrl'] = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
            logger.info("[BuildAssetURLs] Location image loaded")
        else:
            assets['locationUrl'] = None
            logger.warning(f"[BuildAssetURLs] Location image not found. Tried: {location_variations}")
        
        # Host image - try multiple name variations
        host_variations = [host_name, host_name.replace('_', ' '), request.host.lower(), request.host]
        host_variations = list(dict.fromkeys(v for v in host_variations if v))
        
        host_img = None
        for var in host_variations:
            host_img, _ = service._get_host_image(var)
            if host_img:
                break
        
        if host_img:
            host_img = host_img.convert('RGB')
            host_img = service._resize_to_story(host_img)
            import io
            buffer = io.BytesIO()
            host_img.save(buffer, format='PNG')
            assets['hostUrl'] = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
            logger.info("[BuildAssetURLs] Host image loaded")
        else:
            assets['hostUrl'] = None
            logger.warning(f"[BuildAssetURLs] Host image not found. Tried: {host_variations}")
        
        # Background image - try multiple name variations
        bg_variations = [location_name, location_folder_clean]
        bg_variations.extend([v.replace('_', ' ') for v in [location_name, location_folder_clean]])
        bg_variations.append(request.locationFolder.lower().replace(' ', '_'))
        bg_variations = list(dict.fromkeys(v for v in bg_variations if v))
        
        bg_img = None
        for var in bg_variations:
            bg_img = service._get_background_image(var, num_rounds=num_rounds)
            if bg_img:
                break
        
        if bg_img:
            bg_img = bg_img.convert('RGB')
            bg_img = service._resize_to_story(bg_img)
            import io
            buffer = io.BytesIO()
            bg_img.save(buffer, format='PNG')
            assets['backgroundUrl'] = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
            logger.info("[BuildAssetURLs] Background image loaded")
        else:
            assets['backgroundUrl'] = None
            logger.warning(f"[BuildAssetURLs] Background image not found. Tried: {bg_variations}")
        
        return {
            'success': True,
            'assets': assets,
            'numRounds': num_rounds,
            'location': request.location,
            'host': request.host
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting build asset URLs: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate/{presentation_id}")
async def generate_story_video(presentation_id: str, background_tasks: BackgroundTasks) -> Dict:
    """
    Start video generation job (async to avoid Cloudflare timeout).
    Returns immediately with a job_id. Poll /job-status/{job_id} for progress.
    
    Why async? Video generation takes 30-60 seconds. Cloudflare times out at ~100s,
    but network issues can cause 520 errors before that. This pattern:
    1. Returns immediately (< 1 second)
    2. Processes in background
    3. Client polls for status
    """
    import time
    
    try:
        # Validate presentation exists (check both collections)
        presentation = await db.trivia_presentations.find_one({'id': presentation_id})
        if not presentation:
            presentation = await db.presentations.find_one({'id': presentation_id})
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")
        
        # Create job
        job_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        
        video_jobs[job_id] = {
            'status': 'queued',
            'progress': 0,
            'step': 'Initializing...',
            'error': None,
            'result': None,
            'presentation_id': presentation_id,
            'presentation_name': presentation.get('name', 'Unknown'),
            'created_at': now,
            'updated_at': now
        }
        
        logger.info(f"[JOB {job_id}] Created for presentation: {presentation['name']}")
        
        # Prepare story data - include roundNames for proper display
        story_data = {
            'location': presentation.get('location', ''),
            'hostFile': presentation.get('hostFile', ''),
            'roundFiles': presentation.get('roundFiles', []),
            'roundNames': presentation.get('roundNames', []),
            'roundTypes': presentation.get('roundTypes', []),
            'numRounds': presentation.get('numRounds', 5),
            'host': presentation.get('host', ''),
        }
        
        # Start background task
        background_tasks.add_task(
            process_video_generation,
            job_id,
            story_data,
            presentation['name']
        )
        
        return {
            'success': True,
            'message': 'Video generation started',
            'jobId': job_id,
            'statusUrl': f'/api/story-generator/job-status/{job_id}'
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[JOB CREATE] Failed: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to start video generation: {str(e)}")

def process_video_generation(job_id: str, story_data: Dict, presentation_name: str):
    """
    Background task to generate video. Updates job status as it progresses.
    """
    import time
    start_time = time.time()
    
    def update_job(status: str = None, progress: int = None, step: str = None, error: str = None, result: Dict = None):
        if job_id in video_jobs:
            if status:
                video_jobs[job_id]['status'] = status
            if progress is not None:
                video_jobs[job_id]['progress'] = progress
            if step:
                video_jobs[job_id]['step'] = step
            if error:
                video_jobs[job_id]['error'] = error
            if result:
                video_jobs[job_id]['result'] = result
            video_jobs[job_id]['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    try:
        update_job(status='processing', progress=5, step='Loading presentation data...')
        logger.info(f"[JOB {job_id}] Starting video generation for: {presentation_name}")
        
        update_job(progress=10, step='Fetching location image from SharePoint...')
        
        service = get_story_service()
        
        # Generate video with progress updates via callback
        def progress_callback(step_num: int, step_name: str):
            # Map step numbers to progress percentages
            progress_map = {
                2: (20, 'Fetching location image...'),
                3: (35, 'Fetching host image...'),
                4: (50, 'Fetching background image...'),
                5: (65, 'Creating text overlays...'),
                6: (80, 'Encoding video (~15s)...')
            }
            pct, msg = progress_map.get(step_num, (progress_map.get(step_num-1, (10, 'Processing...'))[0] + 5, step_name))
            update_job(progress=pct, step=msg)
            logger.info(f"[JOB {job_id}] Progress: {pct}% - {msg}")
        
        output_path, generation_stats = service.generate_video_with_progress(
            story_data, 
            progress_callback=progress_callback
        )
        
        update_job(progress=95, step='Finalizing video...')
        
        filename = os.path.basename(output_path)
        total_time = time.time() - start_time
        
        update_job(
            status='completed',
            progress=100,
            step='Video ready!',
            result={
                'filename': filename,
                'downloadUrl': f'/api/story-generator/download/{filename}',
                'stats': {
                    'totalTime': round(total_time, 2),
                    **generation_stats
                }
            }
        )
        
        logger.info(f"[JOB {job_id}] COMPLETED in {total_time:.2f}s - {filename}")
        
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[JOB {job_id}] FAILED after {elapsed:.2f}s: {str(e)}")
        import traceback
        logger.error(f"[JOB {job_id}] Traceback:\n{traceback.format_exc()}")
        
        update_job(
            status='failed',
            progress=video_jobs.get(job_id, {}).get('progress', 0),
            step='Generation failed',
            error=str(e)
        )

@router.get("/job-status/{job_id}")
async def get_job_status(job_id: str) -> Dict:
    """
    Get the status of a video generation job.
    Poll this endpoint every 2-3 seconds until status is 'completed' or 'failed'.
    
    Response fields:
    - status: 'queued', 'processing', 'completed', or 'failed'
    - progress: 0-100 percentage
    - step: Current step description
    - error: Error message if failed
    - result: Download info if completed
    """
    if job_id not in video_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = video_jobs[job_id]
    
    response = {
        'jobId': job_id,
        'status': job['status'],
        'progress': job['progress'],
        'step': job['step'],
        'presentationName': job.get('presentation_name', 'Unknown'),
        'createdAt': job['created_at'],
        'updatedAt': job['updated_at']
    }
    
    if job['error']:
        response['error'] = job['error']
    
    if job['result']:
        response['result'] = job['result']
    
    return response

@router.delete("/job/{job_id}")
async def cancel_job(job_id: str) -> Dict:
    """Cancel/clean up a job (removes from memory)."""
    if job_id in video_jobs:
        del video_jobs[job_id]
        return {'success': True, 'message': 'Job removed'}
    raise HTTPException(status_code=404, detail="Job not found")

@router.get("/download/{filename}")
async def download_video(filename: str):
    """
    Download a generated story video.
    """
    try:
        service = get_story_service()
        file_path = service.generated_dir / filename
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Video not found")
        
        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type='video/mp4'
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading video: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload-asset")
async def upload_asset(
    file: UploadFile = File(...),
    asset_type: str = Form(...),
    name: Optional[str] = Form(None)
) -> Dict:
    """
    Upload an asset (location image, host GIF, or background).
    
    Args:
        file: The image/GIF file
        asset_type: 'location', 'host', or 'background'
        name: Optional custom name (will use filename if not provided)
    """
    try:
        # Validate asset type
        if asset_type not in ['location', 'host', 'background']:
            raise HTTPException(status_code=400, detail="Invalid asset type")
        
        # Read file content
        content = await file.read()
        
        # Use custom name if provided
        filename = name or file.filename
        if not filename:
            raise HTTPException(status_code=400, detail="Filename required")
        
        # Ensure proper extension
        if not any(filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
            # Add extension from content type
            ext_map = {
                'image/png': '.png',
                'image/jpeg': '.jpg',
                'image/gif': '.gif',
                'image/webp': '.webp'
            }
            ext = ext_map.get(file.content_type, '.png')
            filename = filename + ext
        
        # Upload asset
        service = get_story_service()
        result = service.upload_asset(content, filename, asset_type)
        
        return {
            'success': True,
            'message': f'{asset_type.title()} asset uploaded successfully',
            'asset': result
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading asset: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/asset/{asset_type}/{asset_id}")
async def delete_asset(asset_type: str, asset_id: str) -> Dict:
    """
    Delete an asset.
    
    Args:
        asset_type: 'location', 'host', or 'background'
        asset_id: Asset ID (filename without extension)
    """
    try:
        if asset_type not in ['location', 'host', 'background']:
            raise HTTPException(status_code=400, detail="Invalid asset type")
        
        service = get_story_service()
        deleted = service.delete_asset(asset_id, asset_type)
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Asset not found")
        
        return {
            'success': True,
            'message': f'{asset_type.title()} asset deleted successfully'
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting asset: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/preview/{presentation_id}")
async def generate_preview(presentation_id: str) -> Dict:
    """
    Generate a preview of the story (returns frame data without creating video).
    Useful for showing a preview before generating the full video.
    """
    try:
        # Get presentation data
        presentation = await db.trivia_presentations.find_one({'id': presentation_id})
        if not presentation:
            presentation = await db.presentations.find_one({'id': presentation_id})
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")
        
        # Get the service for resolving round names
        service = get_story_service()
        
        # Prepare data for preview - resolve actual round names
        round_files = presentation.get('roundFiles', [])
        rounds_info = []
        for rf in round_files:
            round_type = rf.get('type', 'REG')
            round_file = rf.get('file', '')
            
            # For MC and MYS, use fixed names
            if round_type == 'MC':
                round_name = 'Multiple Choice'
            elif round_type == 'MYS':
                round_name = 'Mystery'
            else:
                # For REG, MISC, and BIG - resolve the actual round name from SharePoint
                round_name = service.resolve_round_name(round_file)
                if round_name == 'Unknown' or not round_name:
                    # Fallback to using the stored name or a generic label
                    round_name = rf.get('name', f'{round_type} Round')
            
            rounds_info.append({
                'order': rf.get('order', 0),
                'type': round_type,
                'name': round_name
            })
        
        # Get location name
        location_path = presentation.get('location', '')
        location_name = location_path.split('/')[-1] if location_path else 'Unknown'
        import re
        location_name = re.sub(r'^\d+_', '', location_name)
        
        # Get host name
        host_path = presentation.get('hostFile', '')
        host_name = host_path.split('/')[-1].replace('.pptx', '') if host_path else 'Unknown'
        
        # Check which assets are available
        service = get_story_service()
        assets = service.get_available_assets()
        
        # Normalize names for matching
        location_key = location_name.replace(' ', '_').lower()
        host_key = host_name.replace(' ', '_').lower()
        num_rounds = len(rounds_info)
        
        # Check for location asset - match by folder name
        has_location_asset = any(
            re.sub(r'^\d+_', '', a.get('folder', '')).lower().replace(' ', '_') == location_key or
            location_key in re.sub(r'^\d+_', '', a.get('folder', '')).lower().replace(' ', '_')
            for a in assets['locations']
        )
        
        # Check for host asset
        has_host_asset = any(
            re.sub(r'^\d+_', '', a['id']).lower().replace(' ', '_') == host_key or
            host_key in re.sub(r'^\d+_', '', a['id']).lower().replace(' ', '_')
            for a in assets['hosts']
        )
        
        # Check for background asset - match by folder name AND num_rounds
        has_background_asset = any(
            (re.sub(r'^\d+_', '', a.get('folder', '')).lower().replace(' ', '_') == location_key or
             location_key in re.sub(r'^\d+_', '', a.get('folder', '')).lower().replace(' ', '_')) and
            a.get('numRounds', 0) == num_rounds
            for a in assets['backgrounds']
        )
        
        return {
            'success': True,
            'preview': {
                'location': {
                    'name': location_name,
                    'hasAsset': has_location_asset,
                    'duration': 5
                },
                'host': {
                    'name': host_name,
                    'hasAsset': has_host_asset,
                    'duration': 5
                },
                'rounds': {
                    'items': rounds_info,
                    'hasBackground': has_background_asset,
                    'numRounds': num_rounds,
                    'duration': 15
                },
                'totalDuration': 25
            },
            'assetsNeeded': {
                'locationImage': not has_location_asset,
                'hostImage': not has_host_asset,
                'backgroundImage': not has_background_asset
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating preview: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class AssembleVideoRequest(BaseModel):
    locationName: str
    locationFolder: str
    hostName: str
    rounds: List[dict]
    fps: int = 30
    width: int = 1080
    height: int = 1920
    numRounds: int = 5

# Background job store for video assembly
import threading
_video_jobs = {}

def _run_video_assembly(job_id: str, request_data: dict):
    """Background worker: fetches assets, renders frames, assembles with FFmpeg"""
    import subprocess
    from PIL import Image, ImageDraw, ImageFont
    
    temp_dir = None
    try:
        _video_jobs[job_id]["status"] = "processing"
        _video_jobs[job_id]["progress"] = 5
        
        temp_dir = tempfile.mkdtemp(prefix="story_assemble_")
        # Encode at half resolution for speed — Instagram compresses heavily anyway
        # Full res (1080x1920) times out on production; half res (540x960) is 4x faster
        W = 540
        H = 960
        FPS = request_data["fps"]
        DUR_LOC, DUR_HOST, DUR_ROUNDS = 3, 3, 19
        
        service = get_story_service()
        loc_clean = request_data["locationName"].lower().replace(' ', '_').replace('-', '_')
        loc_folder_clean = re.sub(r'^\d+_', '', request_data["locationFolder"]).lower().replace(' ', '_').replace('-', '_')
        host_clean = request_data["hostName"].lower().replace(' ', '_').replace('-', '_')
        
        logger.info(f"[Assemble:{job_id}] Loc={request_data['locationName']}, Host={request_data['hostName']}")
        _video_jobs[job_id]["progress"] = 10
        
        # Fetch location
        loc_img = None
        for var in [loc_clean, loc_folder_clean, request_data["locationName"], request_data["locationFolder"]]:
            loc_img = service._get_location_image(var)
            if loc_img: break
        _video_jobs[job_id]["progress"] = 20
        
        # Fetch host — GIF first
        host_path = None
        host_is_gif = False
        for var in [host_clean, request_data["hostName"].lower(), request_data["hostName"]]:
            sp_path = service._find_sharepoint_asset('hosts', var, ['.gif'])
            if sp_path:
                content = service._download_sharepoint_file(sp_path)
                if content:
                    host_path = os.path.join(temp_dir, "host.gif")
                    with open(host_path, 'wb') as f: f.write(content)
                    host_is_gif = True
                    break
        if not host_path:
            for var in [host_clean, request_data["hostName"].lower(), request_data["hostName"]]:
                host_img, _ = service._get_host_image(var)
                if host_img:
                    host_path = os.path.join(temp_dir, "host.png")
                    host_img.convert('RGB').resize((W, H), Image.LANCZOS).save(host_path, 'PNG')
                    break
        _video_jobs[job_id]["progress"] = 35
        
        # Fetch background
        bg_img = None
        for var in [loc_clean, loc_folder_clean, request_data["locationName"], request_data["locationFolder"]]:
            bg_img = service._get_background_image(var, num_rounds=request_data.get("numRounds", 5))
            if bg_img: break
        _video_jobs[job_id]["progress"] = 45
        
        # Render location frame
        loc_frame_path = os.path.join(temp_dir, "location.png")
        try: font48 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        except: font48 = ImageFont.load_default()
        try: font42 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42)
        except: font42 = ImageFont.load_default()
        
        if loc_img:
            loc_img.convert('RGB').resize((W, H), Image.LANCZOS).save(loc_frame_path, 'PNG')
        else:
            frame = Image.new('RGB', (W, H), (10, 30, 61))
            draw = ImageDraw.Draw(frame)
            draw.text((W//2, H//2), request_data["locationName"], fill='white', anchor='mm', font=font48)
            frame.save(loc_frame_path, 'PNG')
        
        if not host_path:
            host_path = os.path.join(temp_dir, "host.png")
            frame = Image.new('RGB', (W, H), (10, 10, 40))
            draw = ImageDraw.Draw(frame)
            draw.text((W//2, H//2), request_data["hostName"], fill='white', anchor='mm', font=font48)
            frame.save(host_path, 'PNG')
        _video_jobs[job_id]["progress"] = 55
        
        # Render rounds frame
        rounds_frame_path = os.path.join(temp_dir, "rounds.png")
        frame = bg_img.convert('RGB').resize((W, H), Image.LANCZOS) if bg_img else Image.new('RGB', (W, H), (10, 30, 61))
        overlay = Image.new('RGBA', (W, H), (0, 0, 0, 128))
        frame = Image.alpha_composite(frame.convert('RGBA'), overlay).convert('RGB')
        draw = ImageDraw.Draw(frame)
        
        rounds = request_data.get("rounds", [])
        num_r = len(rounds)
        box_w, box_h = 600, 70
        box_x = (W - box_w) // 2
        gap = 80 if num_r >= 6 else 120
        total_h = (num_r * box_h) + ((num_r - 1) * gap)
        start_y = (H - total_h) // 2 + 50
        for i, r in enumerate(rounds):
            y = start_y + i * (box_h + gap)
            try: rgb = tuple(int(r.get('color', '#FF6B6B').lstrip('#')[j:j+2], 16) for j in (0, 2, 4))
            except: rgb = (255, 107, 107)
            draw.rounded_rectangle([(box_x, y), (box_x + box_w, y + box_h)], radius=12, fill=rgb)
            name = r.get('name', f'Round {i+1}')
            bbox = font42.getbbox(name)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((box_x + (box_w - tw) // 2, y + (box_h - th) // 2), name, fill='black', font=font42)
        frame.save(rounds_frame_path, 'PNG')
        _video_jobs[job_id]["progress"] = 65
        
        # ========== FAST FFmpeg PIPELINE ==========
        # Strategy: encode each section as a short MP4 clip individually (fast, ~3-5s each)
        # then concat them (instant, no re-encoding). Total: ~15-20s.
        # This avoids the CPU-intensive xfade filter that times out on production.
        
        output_path = os.path.join(temp_dir, "output.mp4")
        sf = "scale=1080:1920,setsar=1"
        encode_opts = ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', '-pix_fmt', 'yuv420p', '-r', str(FPS), '-an']
        
        # Step 1: Encode location clip (3s)
        loc_clip = os.path.join(temp_dir, "clip_loc.mp4")
        subprocess.run([
            'ffmpeg', '-y', '-loop', '1', '-t', str(DUR_LOC), '-i', loc_frame_path,
            '-vf', sf, *encode_opts, loc_clip
        ], capture_output=True, text=True, timeout=30)
        _video_jobs[job_id]["progress"] = 72
        logger.info(f"[Assemble:{job_id}] Location clip done")
        
        # Step 2: Encode host clip (3s)
        host_clip = os.path.join(temp_dir, "clip_host.mp4")
        if host_is_gif:
            # Pre-convert GIF to fixed-duration clip
            subprocess.run([
                'ffmpeg', '-y', '-stream_loop', '-1', '-t', str(DUR_HOST), '-i', host_path,
                '-vf', sf, *encode_opts, host_clip
            ], capture_output=True, text=True, timeout=30)
        else:
            subprocess.run([
                'ffmpeg', '-y', '-loop', '1', '-t', str(DUR_HOST), '-i', host_path,
                '-vf', sf, *encode_opts, host_clip
            ], capture_output=True, text=True, timeout=30)
        _video_jobs[job_id]["progress"] = 80
        logger.info(f"[Assemble:{job_id}] Host clip done (gif={host_is_gif})")
        
        # Step 3: Encode rounds clip (19s) — longest clip, needs more timeout
        rounds_clip = os.path.join(temp_dir, "clip_rounds.mp4")
        subprocess.run([
            'ffmpeg', '-y', '-loop', '1', '-t', str(DUR_ROUNDS), '-i', rounds_frame_path,
            '-vf', sf, *encode_opts, rounds_clip
        ], capture_output=True, text=True, timeout=120)
        _video_jobs[job_id]["progress"] = 88
        logger.info(f"[Assemble:{job_id}] Rounds clip done")
        
        # Step 4: Concat all clips (instant — no re-encoding)
        concat_file = os.path.join(temp_dir, "concat.txt")
        with open(concat_file, 'w') as f:
            f.write(f"file '{loc_clip}'\nfile '{host_clip}'\nfile '{rounds_clip}'\n")
        
        concat_result = subprocess.run([
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_file,
            '-c', 'copy', '-movflags', '+faststart', output_path
        ], capture_output=True, text=True, timeout=30)
        
        if concat_result.returncode != 0:
            # Log the actual error for debugging
            err_msg = concat_result.stderr[-300:] if concat_result.stderr else "Unknown error"
            logger.error(f"[Assemble:{job_id}] Concat failed: {err_msg}")
            raise Exception(f"Video concat failed: {err_msg}")
        
        _video_jobs[job_id]["progress"] = 92
        logger.info(f"[Assemble:{job_id}] Concat done")
        
        _video_jobs[job_id]["progress"] = 90
        with open(output_path, 'rb') as f: mp4_bytes = f.read()
        mp4_b64 = base64.b64encode(mp4_bytes).decode('utf-8')
        
        logger.info(f"[Assemble:{job_id}] ✅ {len(mp4_bytes)//1024}KB")
        _video_jobs[job_id].update({
            "status": "complete", "progress": 100,
            "result": {"success": True, "video_data": f"data:video/mp4;base64,{mp4_b64}",
                        "size_bytes": len(mp4_bytes), "filename": f"story_{uuid.uuid4().hex[:8]}.mp4"}
        })
    except Exception as e:
        logger.error(f"[Assemble:{job_id}] Error: {e}")
        _video_jobs[job_id].update({"status": "error", "error": str(e)})
    finally:
        if temp_dir and os.path.exists(temp_dir):
            import shutil; shutil.rmtree(temp_dir, ignore_errors=True)

@router.post("/assemble-video")
async def assemble_video(request: AssembleVideoRequest):
    """Start video assembly as background job — returns immediately to avoid proxy timeout."""
    job_id = str(uuid.uuid4())[:12]
    _video_jobs[job_id] = {"status": "queued", "progress": 0, "result": None, "error": None}
    thread = threading.Thread(target=_run_video_assembly, args=(job_id, request.model_dump()), daemon=True)
    thread.start()
    return {"success": True, "job_id": job_id}

@router.get("/assemble-video/status/{job_id}")
async def get_assembly_status(job_id: str):
    """Poll for video assembly progress."""
    job = _video_jobs.get(job_id)
    if not job: raise HTTPException(status_code=404, detail="Job not found")
    resp = {"status": job["status"], "progress": job["progress"]}
    if job["status"] == "complete":
        resp["result"] = job["result"]
        threading.Timer(300, lambda: _video_jobs.pop(job_id, None)).start()
    elif job["status"] == "error":
        resp["error"] = job["error"]
        _video_jobs.pop(job_id, None)
    return resp

# ========== LIGHTWEIGHT WEBM → MP4 CONVERSION ==========
# Client records WebM on user's hardware, server just transcodes to MP4

class WebmConvertRequest(BaseModel):
    video_data: str
    filename: Optional[str] = "story_video"

@router.post("/convert-webm")
async def convert_webm_to_mp4(request: WebmConvertRequest):
    """Fast WebM to MP4 transcode. Client does the heavy recording, server just converts format."""
    import subprocess
    
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="webm_convert_")
        
        # Decode base64
        if request.video_data.startswith('data:'):
            b64 = request.video_data.split(',', 1)[1]
        else:
            b64 = request.video_data
        
        webm_bytes = base64.b64decode(b64)
        webm_path = os.path.join(temp_dir, "input.webm")
        mp4_path = os.path.join(temp_dir, "output.mp4")
        
        with open(webm_path, 'wb') as f:
            f.write(webm_bytes)
        
        logger.info(f"[WebmConvert] Input: {len(webm_bytes) // 1024}KB")
        
        # Fast transcode — just change container format, minimal re-encoding
        result = subprocess.run([
            'ffmpeg', '-y', '-i', webm_path,
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
            '-an', mp4_path
        ], capture_output=True, text=True, timeout=120)
        
        if result.returncode != 0:
            logger.error(f"[WebmConvert] FFmpeg error: {result.stderr[-200:]}")
            raise HTTPException(status_code=500, detail=f"Conversion failed: {result.stderr[-100:]}")
        
        with open(mp4_path, 'rb') as f:
            mp4_bytes = f.read()
        
        mp4_b64 = base64.b64encode(mp4_bytes).decode('utf-8')
        logger.info(f"[WebmConvert] Output: {len(mp4_bytes) // 1024}KB")
        
        return {
            "success": True,
            "video_data": f"data:video/mp4;base64,{mp4_b64}",
            "size_bytes": len(mp4_bytes),
            "filename": f"{request.filename}.mp4"
        }
    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Conversion timed out")
    except Exception as e:
        logger.error(f"[WebmConvert] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_dir and os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

# ========== TEMPORARY VIDEO FILE STORAGE FOR QR DOWNLOAD ==========
# Stores MP4 files temporarily so mobile devices can download via QR code scan
import time

_temp_video_store = {}  # {file_id: {"path": str, "created": float, "filename": str}}
_TEMP_VIDEO_TTL = 3600  # 1 hour TTL

def _cleanup_expired_videos():
    """Remove expired temp video files"""
    now = time.time()
    expired = [fid for fid, info in _temp_video_store.items() if now - info["created"] > _TEMP_VIDEO_TTL]
    for fid in expired:
        try:
            path = _temp_video_store[fid]["path"]
            if os.path.exists(path):
                os.unlink(path)
            del _temp_video_store[fid]
            logger.info(f"[TempVideo] Cleaned up expired file: {fid}")
        except Exception as e:
            logger.warning(f"[TempVideo] Cleanup error for {fid}: {e}")

class StoreVideoRequest(BaseModel):
    video_data: str  # base64 data URL
    filename: Optional[str] = "story_video"

@router.post("/store-temp")
async def store_temp_video(request: StoreVideoRequest):
    """
    Store an MP4 video temporarily for QR code download.
    Returns a file_id that can be used to download the file.
    """
    try:
        # Cleanup expired files first
        _cleanup_expired_videos()
        
        # Decode base64
        if request.video_data.startswith('data:'):
            video_base64 = request.video_data.split(',', 1)[1]
        else:
            video_base64 = request.video_data
        
        video_bytes = base64.b64decode(video_base64)
        
        # Generate unique file ID and save
        file_id = str(uuid.uuid4())[:12]
        temp_dir = os.path.join(tempfile.gettempdir(), "story_videos")
        os.makedirs(temp_dir, exist_ok=True)
        
        file_path = os.path.join(temp_dir, f"{file_id}.mp4")
        with open(file_path, 'wb') as f:
            f.write(video_bytes)
        
        _temp_video_store[file_id] = {
            "path": file_path,
            "created": time.time(),
            "filename": f"{request.filename}.mp4"
        }
        
        logger.info(f"[TempVideo] Stored {len(video_bytes)} bytes as {file_id}")
        
        return {
            "success": True,
            "file_id": file_id,
            "expires_in": _TEMP_VIDEO_TTL
        }
        
    except Exception as e:
        logger.error(f"[TempVideo] Store error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/qr-download/{file_id}")
async def download_temp_video(file_id: str):
    """
    Download a temporarily stored video file.
    Used by mobile devices scanning the QR code.
    """
    # Don't cleanup during download — prevents file deletion while serving
    
    # Check in-memory store first
    info = _temp_video_store.get(file_id)
    if info and os.path.exists(info["path"]):
        logger.info(f"[TempVideo] Serving from memory store: {file_id}")
        return FileResponse(
            info["path"],
            media_type="video/mp4",
            filename=info["filename"],
            headers={"Content-Disposition": f'attachment; filename="{info["filename"]}"'}
        )
    
    # Fallback: check filesystem directly (survives server restarts)
    temp_dir = os.path.join(tempfile.gettempdir(), "story_videos")
    file_path = os.path.join(temp_dir, f"{file_id}.mp4")
    
    if os.path.exists(file_path):
        file_age = time.time() - os.path.getmtime(file_path)
        if file_age < _TEMP_VIDEO_TTL:
            logger.info(f"[TempVideo] Serving from filesystem: {file_id} (age={file_age:.0f}s)")
            return FileResponse(
                file_path,
                media_type="video/mp4",
                filename=f"story_{file_id}.mp4",
                headers={"Content-Disposition": f'attachment; filename="story_{file_id}.mp4"'}
            )
        else:
            os.unlink(file_path)
    
    logger.warning(f"[TempVideo] Not found: {file_id}")
    raise HTTPException(status_code=404, detail="Video not found or expired")

