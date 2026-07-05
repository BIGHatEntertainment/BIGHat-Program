"""
Trivia Import Routes - Handles slide loading from GridFS cache
Slide generation is done by slide_fetcher.py (on-demand section-by-section)
"""
from fastapi import APIRouter, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

from gridfs_service import get_gridfs_service

router = APIRouter(prefix="/trivia-import", tags=["trivia-import"])
logger = logging.getLogger(__name__)

db: AsyncIOMotorDatabase = None

def set_database(database):
    global db
    db = database


@router.get("/chunk/{presentation_id}/{chunk_number}")
async def get_slide_chunk(presentation_id: str, chunk_number: int):
    """Get a specific chunk of slides from GridFS"""
    try:
        gridfs = get_gridfs_service()
        chunk_data = await gridfs.get_slide_chunk(presentation_id, chunk_number)
        
        if chunk_data:
            return {
                "chunkNumber": chunk_number,
                "slides": chunk_data['slides'],
                "slidesCount": len(chunk_data['slides'])
            }
        
        # v32.0.0-alpha.44: NATIVE fallback — chunk chunk_number of the
        # on-disk assembled slide list (chunks of 20 slides each).
        try:
            from routes.trivia_viewer import _assemble_slides_native
            native = await _assemble_slides_native(presentation_id)
            all_slides = native.get("slides") or []
            CHUNK = 20
            start = chunk_number * CHUNK
            end = start + CHUNK
            piece = all_slides[start:end]
            if piece:
                return {
                    "chunkNumber": chunk_number,
                    "slides": piece,
                    "slidesCount": len(piece),
                    "source": "native-disk",
                }
        except Exception as e:
            logger.warning("[trivia-import chunk] native fallback failed: %s", e)

        raise HTTPException(status_code=404, detail=f"Chunk {chunk_number} not found")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting slide chunk: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/slides-metadata/{presentation_id}")
async def get_slides_metadata(presentation_id: str):
    """Get metadata about slides (for chunked loading)"""
    try:
        gridfs = get_gridfs_service()
        metadata = await gridfs.get_slides_metadata(presentation_id)
        
        if metadata:
            return {
                "hasGridFSSlides": True,
                "totalSlides": metadata['total_slides'],
                "totalChunks": metadata['total_chunks'],
                "originalSize": metadata['original_size'],
                "compressedSize": metadata['compressed_size'],
                "chunks": metadata['chunks']
            }

        # v32.0.0-alpha.44: fall through to native disk metadata.
        try:
            from routes.trivia_viewer import _assemble_slides_native
            native = await _assemble_slides_native(presentation_id)
            total = len(native.get("slides") or [])
            if total:
                CHUNK = 20
                total_chunks = max(1, (total + CHUNK - 1) // CHUNK)
                return {
                    "hasGridFSSlides": False,
                    "totalSlides": total,
                    "totalChunks": total_chunks,
                    "source": "native-disk",
                }
        except Exception as e:
            logger.warning("[trivia-import metadata] native fallback failed: %s", e)

        return {
            "hasGridFSSlides": False,
            "totalSlides": 0,
            "totalChunks": 0
        }
    
    except Exception as e:
        logger.warning(f"Slides metadata not available: {str(e)}")
        return {
            "hasGridFSSlides": False,
            "totalSlides": 0,
            "totalChunks": 0
        }


@router.get("/generation-status/{presentation_id}")
async def get_generation_status(presentation_id: str):
    """Get the current slide generation status for progressive loading"""
    try:
        status = await db.slide_generation_status.find_one(
            {"presentationId": presentation_id},
            {"_id": 0}
        )
        
        if status:
            return status
        
        # Check if slides are already in GridFS (generation complete)
        gridfs = get_gridfs_service()
        metadata = await gridfs.get_slides_metadata(presentation_id)
        
        if metadata:
            return {
                "presentationId": presentation_id,
                "status": "complete",
                "totalSlides": metadata['total_slides'],
                "sections": {}
            }
        
        return {
            "presentationId": presentation_id,
            "status": "not_started",
            "sections": {}
        }
    
    except Exception as e:
        logger.error(f"Error getting generation status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/section/{presentation_id}/{section_name}")
async def get_section_metadata(presentation_id: str, section_name: str):
    """Get section metadata (for progress tracking)"""
    try:
        section = await db.slides_sections.find_one(
            {"presentationId": presentation_id, "section": section_name},
            {"_id": 0}
        )
        
        if section:
            return {
                "section": section_name,
                "slidesCount": section.get("slidesCount", 0),
                "status": "complete"
            }
        
        raise HTTPException(status_code=404, detail=f"Section {section_name} not found")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting section metadata: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/slides/{presentation_id}")
async def get_imported_slides(presentation_id: str):
    """
    Get slides for a trivia presentation from GridFS cache.
    Returns chunked metadata for large presentations.
    """
    try:
        gridfs = get_gridfs_service()
        
        # Check GridFS cache
        metadata = await gridfs.get_slides_metadata(presentation_id)
        if metadata:
            if metadata['total_chunks'] == 1:
                # Small presentation - return all slides
                slides = await gridfs.get_all_slides(presentation_id)
                if slides:
                    logger.info(f"✅ Returning {len(slides)} slides from GridFS cache")
                    return {
                        "slides": slides,
                        "totalSlides": len(slides),
                        "fromCache": True
                    }
            else:
                # Large presentation - return metadata for chunked loading
                logger.info(f"📦 Large presentation ({metadata['total_chunks']} chunks)")
                return {
                    "slides": [],
                    "totalSlides": metadata['total_slides'],
                    "chunked": True,
                    "totalChunks": metadata['total_chunks'],
                    "chunks": metadata['chunks']
                }
        
        # No slides in cache - check generation status
        status = await db.slide_generation_status.find_one(
            {"presentationId": presentation_id},
            {"_id": 0}
        )
        
        if status and status.get('status') == 'generating':
            return {
                "slides": [],
                "totalSlides": 0,
                "status": "generating",
                "message": "Slides are being generated. Please wait."
            }
        
        # v32.0.0-alpha.44: NATIVE fallback — assemble slides from the
        # on-disk `.bighat` manifest + round files. The Editor.jsx expects
        # this endpoint to return {slides, totalSlides, fromCache} so it
        # can render without hitting SharePoint. Delegate to the native
        # assembler already used by `/api/trivia-viewer/{id}/slides`.
        try:
            from routes.trivia_viewer import _assemble_slides_native
            native = await _assemble_slides_native(presentation_id)
            if native and native.get("slides"):
                logger.info("[trivia-import] native disk assembly: %d slides for %s",
                            len(native["slides"]), presentation_id)
                return {
                    "slides": native["slides"],
                    "totalSlides": native["totalSlides"],
                    "fromCache": False,
                    "source": "native-disk",
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("[trivia-import] native fallback failed: %s", e)

        # No cache and not generating - return error
        raise HTTPException(
            status_code=404, 
            detail="Slides not found. Please try creating a new presentation."
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting slides: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



@router.delete("/clear-cache/{presentation_id}")
async def clear_presentation_cache(presentation_id: str):
    """Clear the GridFS cache for a specific presentation"""
    try:
        gridfs = get_gridfs_service()
        
        # Delete all cached slides for this presentation
        deleted_count = await gridfs.delete_presentation_slides(presentation_id)
        
        # Also clear any generation status
        await db.slide_generation_status.delete_many({"presentationId": presentation_id})
        await db.slides_sections.delete_many({"presentationId": presentation_id})
        
        logger.info(f"✅ Cleared cache for presentation {presentation_id}")
        
        return {
            "success": True,
            "message": f"Cache cleared for presentation {presentation_id}",
            "deletedChunks": deleted_count
        }
    
    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear-all-cache")
async def clear_all_cache():
    """Clear ALL GridFS cache (admin endpoint)"""
    try:
        gridfs = get_gridfs_service()
        
        # Delete all cached slides
        deleted_count = await gridfs.delete_all_slides()
        
        # Clear all generation status
        await db.slide_generation_status.delete_many({})
        await db.slides_sections.delete_many({})
        
        logger.info(f"✅ Cleared ALL cache - {deleted_count} items deleted")
        
        return {
            "success": True,
            "message": "All cache cleared",
            "deletedItems": deleted_count
        }
    
    except Exception as e:
        logger.error(f"Error clearing all cache: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
