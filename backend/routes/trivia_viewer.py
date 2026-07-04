from fastapi import APIRouter, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Dict
import logging
import tempfile
import os

from sharepoint_service import SharePointService
from hybrid_pptx_converter import get_hybrid_converter

router = APIRouter(prefix="/trivia-viewer", tags=["trivia-viewer"])
logger = logging.getLogger(__name__)

db: AsyncIOMotorDatabase = None

def set_database(database):
    global db
    db = database


@router.get("/list")
async def list_trivia_presentations(userName: str = "", viewAll: bool = False, hostName: str = "") -> List[Dict]:
    """List trivia presentations filtered by host assignment.
    Hidden presentations are ALWAYS excluded (even for admins with viewAll).
    """
    try:
        from datetime import datetime as dt
        now = dt.utcnow()
        
        # ALWAYS exclude hidden - deleted means deleted
        hidden_filter = {'$or': [{'hidden': {'$ne': True}}, {'hidden': {'$exists': False}}]}
        
        # Build the name match - try multiple variants of the user's name
        name_to_match = hostName or userName
        name_variants = []
        if name_to_match:
            # Full name: "Nicholas Sellards"
            name_variants.append(name_to_match)
            # First name: "Nicholas"
            parts = name_to_match.split()
            if parts:
                name_variants.append(parts[0])
            # Look up employee record by email for the short name (e.g., "Nick S.")
            try:
                # First try to find by the hub user's email
                hub_user = await db.users.find_one(
                    {'name': {'$regex': f'^{name_to_match}', '$options': 'i'}},
                    {'_id': 0, 'email': 1}
                )
                if hub_user and hub_user.get('email'):
                    emp = await db.employees.find_one(
                        {'email': {'$regex': f'^{hub_user["email"]}$', '$options': 'i'}},
                        {'_id': 0, 'name': 1}
                    )
                    if emp and emp.get('name') and emp['name'] not in name_variants:
                        name_variants.append(emp['name'])
                        # Also add first part of employee name
                        emp_first = emp['name'].split()[0]
                        if emp_first not in name_variants:
                            name_variants.append(emp_first)
            except:
                pass
            # Also match userName (short lowercase)
            if userName and userName not in name_variants:
                name_variants.append(userName)
        
        logger.info(f"Trivia list: viewAll={viewAll} hostName='{hostName}' variants={name_variants}")
        
        if viewAll:
            # Admin viewAll: show all non-hidden presentations
            base_filter = hidden_filter
            pres_filter = {'$and': [{'type': 'trivia-imported'}, hidden_filter]}
        else:
            if name_variants:
                # Build OR conditions for all name variants
                host_conditions = []
                for nv in name_variants:
                    host_conditions.append({'host': {'$regex': nv, '$options': 'i'}})
                    host_conditions.append({'createdBy': {'$regex': nv, '$options': 'i'}})
                
                base_filter = {'$and': [hidden_filter, {'$or': host_conditions}]}
                pres_filter = {'$and': [{'type': 'trivia-imported'}, hidden_filter, {'$or': host_conditions}]}
            else:
                base_filter = {'$and': [hidden_filter, {'host': {'$exists': False}}]}  # Match nothing
                pres_filter = {'$and': [{'type': 'trivia-imported'}, hidden_filter, {'host': {'$exists': False}}]}
        
        # Get from both collections
        trivia_pres = await db.trivia_presentations.find(base_filter).sort('createdAt', -1).to_list(100)
        imported_pres = await db.presentations.find(pres_filter).sort('createdAt', -1).to_list(100)
        
        # Merge, deduplicating by id
        seen_ids = set()
        all_pres = []
        for p in trivia_pres + imported_pres:
            pid = p.get('id', '')
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                
                # Check autoHideAt in Python (handles both datetime and string)
                auto_hide = p.get('autoHideAt')
                if auto_hide:
                    if isinstance(auto_hide, str):
                        try:
                            auto_hide = dt.fromisoformat(auto_hide.replace('Z', '+00:00').replace('+00:00', ''))
                        except:
                            auto_hide = None
                    if auto_hide and auto_hide < now:
                        continue  # Skip auto-hidden presentations
                
                all_pres.append(p)
        
        # Sort by createdAt descending (handle mixed types)
        def sort_key(x):
            ca = x.get('createdAt', '')
            if isinstance(ca, dt):
                return ca.isoformat()
            return str(ca)
        all_pres.sort(key=sort_key, reverse=True)
        
        logger.info(f"Found {len(all_pres)} trivia presentations ({len(trivia_pres)} trivia + {len(imported_pres)} imported)")
        
        # v32.0.0-alpha.39: also scan the on-disk `.bighat` manifest folder.
        # The disk is the source of truth per merchant spec — if the DB
        # never got the row (native pymongo swap timing), the presenter
        # must still surface the file the wizard just wrote.
        seen_id_set = set(x.get('id', '') for x in all_pres)
        try:
            from pathlib import Path
            import json
            from native.files_router import _docs_root as _dr
            _root = _dr()
            if _root.exists() or _root.parent.exists():
                rounds_dir = _root / "Files" / "Trivia" / "Rounds"
                if rounds_dir.exists():
                    for entry in sorted(rounds_dir.iterdir()):
                        if not entry.is_file() or entry.suffix.lower() != ".bighat":
                            continue
                        try:
                            disk = json.loads(entry.read_text(encoding="utf-8"))
                        except (OSError, ValueError) as e:
                            logger.warning("[trivia-viewer] bad .bighat %s: %s", entry, e)
                            continue
                        pid = disk.get("id") or ""
                        if pid and pid in seen_id_set:
                            continue
                        # Filter by userName / hostName unless viewAll
                        if not viewAll and name_variants:
                            cb = (disk.get("createdBy") or "").lower()
                            host = (disk.get("host") or "").lower()
                            if not any(nv.lower() in cb or nv.lower() in host for nv in name_variants):
                                continue
                        if pid:
                            seen_id_set.add(pid)
                        disk["_disk_path"] = str(entry)
                        all_pres.append(disk)
            logger.info(f"[trivia-viewer] disk scan appended {len(all_pres) - len(trivia_pres) - len(imported_pres)} new entries from Files/Trivia/Rounds/")
        except Exception as e:
            logger.warning("[trivia-viewer] disk scan failed: %s", e)
        
        result = []
        for p in all_pres:
            loc = p.get('location', '')
            if '/' in loc:
                loc = loc.split('/')[-1]
            result.append({
                'id': p.get('id', ''),
                'name': p.get('name', ''),
                'createdBy': p.get('createdBy', ''),
                'host': p.get('host', ''),
                'createdAt': p.get('createdAt', '').isoformat() if isinstance(p.get('createdAt'), dt) else str(p.get('createdAt', '')),
                'totalSlides': p.get('totalSlides', 0),
                'location': loc,
                'roundTypes': p.get('roundTypes', []),
                'roundNames': p.get('roundNames', []),
                'numRounds': p.get('numRounds', 0),
            })
        return result
    
    except Exception as e:
        logger.error(f"Error listing presentations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{presentation_id}")
async def get_trivia_presentation(presentation_id: str) -> Dict:
    """
    Get trivia presentation details including location and round configuration.
    Used by the editor to fetch location for overlay functionality and score tracker configuration.
    """
    try:
        from datetime import datetime as dt
        presentation = await db.trivia_presentations.find_one({'id': presentation_id})
        if not presentation:
            presentation = await db.presentations.find_one({'id': presentation_id})
        if not presentation:
            # v32.0.0-alpha.39: fall back to the on-disk .bighat manifest.
            # Disk is source of truth per merchant spec.
            try:
                from pathlib import Path
                import json
                from native.files_router import _docs_root as _dr
                _root = _dr()
                rounds_dir = _root / "Files" / "Trivia" / "Rounds"
                if rounds_dir.exists():
                    for entry in rounds_dir.iterdir():
                        if entry.suffix.lower() != ".bighat":
                            continue
                        try:
                            data = json.loads(entry.read_text(encoding="utf-8"))
                        except (OSError, ValueError):
                            continue
                        if data.get("id") == presentation_id:
                            presentation = data
                            presentation["_disk_path"] = str(entry)
                            break
            except Exception as e:
                logger.warning("[trivia-viewer] disk lookup failed: %s", e)
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")
        
        created_at = presentation.get('createdAt', '')
        if isinstance(created_at, dt):
            created_at = created_at.isoformat()
        
        return {
            "id": presentation.get('id', ''),
            "name": presentation.get('name', ''),
            "createdBy": presentation.get('createdBy', ''),
            "createdAt": str(created_at),
            "location": presentation.get('location', ''),
            "locationFile": presentation.get('locationFile', ''),
            "locationFolder": presentation.get('locationFolder', ''),
            "totalSlides": presentation.get('totalSlides', 0),
            "numRounds": presentation.get('numRounds'),
            "roundTypes": presentation.get('roundTypes', []),
            "roundNames": presentation.get('roundNames', []),
            "roundFiles": presentation.get('roundFiles', []),
            "hostFile": presentation.get('hostFile', ''),
            "host": presentation.get('host', '')
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching trivia presentation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{presentation_id}/slides")
async def get_presentation_slides(presentation_id: str) -> Dict:
    """
    Generate slides for a trivia presentation on-demand.
    Downloads files from SharePoint, converts to 16:9 images with overlays.
    """
    try:
        # Get presentation from database
        presentation = await db.trivia_presentations.find_one({'id': presentation_id})
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")

        sp = SharePointService()
        converter = get_hybrid_converter()
        temp_dir = tempfile.mkdtemp(prefix="trivia_view_")

        all_slides = []
        slide_order = 0

        try:
            # 1. Host slide
            if presentation.get('hostFile'):
                host_local = os.path.join(temp_dir, "host.pptx")
                if sp.download_file(presentation['hostFile'], host_local):
                    host_slides = converter.convert_pptx_to_slides(host_local, slide_order)
                    all_slides.extend(host_slides)
                    slide_order += len(host_slides)

            # 2. Location slide
            if presentation.get('locationFile'):
                location_local = os.path.join(temp_dir, "location.pptx")
                if sp.download_file(presentation['locationFile'], location_local):
                    location_slides = converter.convert_pptx_to_slides(location_local, slide_order)
                    all_slides.extend(location_slides)
                    slide_order += len(location_slides)

            # 3. Round slides with overlays and sponsors
            round_files = presentation.get('roundFiles', [])
            sponsor_files = presentation.get('sponsorFiles', [])
            sponsor_idx = 0

            for round_info in round_files:
                # Download round file
                round_local = os.path.join(temp_dir, f"round_{round_info['order']}.pptx")
                if sp.download_file(round_info['file'], round_local):
                    # Download overlay if specified
                    overlay_local = None
                    if round_info.get('overlayFile'):
                        overlay_local = os.path.join(temp_dir, f"overlay_{round_info['order']}.png")
                        if not sp.download_file(round_info['overlayFile'], overlay_local):
                            logger.warning(f"Could not download overlay: {round_info['overlayFile']}")
                            overlay_local = None

                    # Convert with overlay (enforces 16:9)
                    round_slides = converter.convert_pptx_to_slides(round_local, slide_order, overlay_local)
                    all_slides.extend(round_slides)
                    slide_order += len(round_slides)

                # Add sponsor after every other round
                if round_info['order'] % 2 == 0 and sponsor_idx < len(sponsor_files):
                    sponsor_local = os.path.join(temp_dir, f"sponsor_{sponsor_idx}.pptx")
                    if sp.download_file(sponsor_files[sponsor_idx], sponsor_local):
                        sponsor_slides = converter.convert_pptx_to_slides(sponsor_local, slide_order)
                        all_slides.extend(sponsor_slides)
                        slide_order += len(sponsor_slides)
                    sponsor_idx += 1

            return {
                "id": presentation['id'],
                "name": presentation['name'],
                "slides": [slide.model_dump() for slide in all_slides],
                "totalSlides": len(all_slides),
                "aspectRatio": "16:9",
                "resolution": "1920x1080"
            }
        
        finally:
            # Cleanup
            converter.cleanup()
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except OSError:
                pass
    
    except Exception as e:
        logger.error(f"Error generating presentation slides: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate slides: {str(e)}")


@router.delete("/delete/{presentation_id}")
async def delete_trivia_presentation(presentation_id: str) -> Dict:
    """
    Delete a trivia presentation and its associated entries.
    Deletes both trivia_presentation and the lightweight presentations entry.
    """
    try:
        # Delete from trivia_presentations collection
        trivia_result = await db.trivia_presentations.delete_one({'id': presentation_id})
        
        # Also delete from presentations collection (created for on-demand loading)
        pres_result = await db.presentations.delete_one({'id': presentation_id})
        
        if trivia_result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Trivia presentation not found")
        
        logger.info(f"Deleted trivia presentation {presentation_id} from both collections")
        logger.info(f"  - trivia_presentations: {trivia_result.deleted_count} deleted")
        logger.info(f"  - presentations: {pres_result.deleted_count} deleted")
        
        return {
            "message": "Trivia presentation deleted successfully",
            "id": presentation_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting trivia presentation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/hide/{presentation_id}")
async def hide_trivia_presentation(presentation_id: str) -> Dict:
    """Hide a presentation from the trivia lobby. Does NOT delete round usage data."""
    try:
        # Hide in BOTH collections
        r1 = await db.trivia_presentations.update_one(
            {'id': presentation_id},
            {'$set': {'hidden': True}}
        )
        r2 = await db.presentations.update_one(
            {'id': presentation_id},
            {'$set': {'hidden': True}}
        )
        if r1.matched_count == 0 and r2.matched_count == 0:
            raise HTTPException(status_code=404, detail="Presentation not found")
        return {"message": "Presentation removed from lobby", "id": presentation_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/complete/{presentation_id}")
async def mark_presentation_complete(presentation_id: str) -> Dict:
    """Mark a presentation as completed (Save & Exit). Will auto-hide after 3 days."""
    from datetime import timedelta
    try:
        now = datetime.utcnow()
        auto_hide_at = now + timedelta(days=3)
        result = await db.trivia_presentations.update_one(
            {'id': presentation_id},
            {'$set': {'completedAt': now.isoformat(), 'autoHideAt': auto_hide_at.isoformat()}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Presentation not found")
        return {"message": "Presentation marked complete. Will auto-hide in 3 days.", "id": presentation_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
