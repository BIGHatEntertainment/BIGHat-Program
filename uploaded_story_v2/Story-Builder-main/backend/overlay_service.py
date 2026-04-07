"""
Overlay Service - Manages location-specific overlays for trivia presentations
Fetches PNG/GIF overlays from SharePoint and applies them to slides
"""
import logging
from typing import List, Dict, Optional, Tuple
from sharepoint_service import SharePointService
import re

logger = logging.getLogger(__name__)

# Global cache for overlay images (persists across requests)
_overlay_image_cache = {}


class OverlayService:
    """Service for managing presentation overlays"""
    
    def __init__(self):
        self.sp = SharePointService()
        # Use global cache so it persists across requests
        self._overlay_cache = _overlay_image_cache
    
    def get_location_overlays(self, location_name: str) -> List[Dict[str, str]]:
        """
        Get all available overlays for a specific location
        
        Args:
            location_name: Name of the location (e.g., "Chicago", "New York")
            
        Returns:
            List of overlay files with metadata
        """
        try:
            # Construct path to location's overlay folder
            overlay_folder = f"01_Trivia/Web App/00_Builder/02_Locations/{location_name}"
            
            logger.info(f"🔍 Fetching overlays from: {overlay_folder}")
            
            # List all files in the location folder
            items = self.sp.list_folder_contents(overlay_folder)
            
            overlays = []
            for item in items:
                # Look for PNG and GIF files
                if item.get('file'):
                    file_name = item['name'].lower()
                    if file_name.endswith('.png') or file_name.endswith('.gif'):
                        # Extract round info from filename if present
                        round_number = self._extract_round_number(item['name'])
                        
                        overlays.append({
                            'id': item['id'],
                            'name': item['name'],
                            'path': f"{overlay_folder}/{item['name']}",
                            'type': 'gif' if file_name.endswith('.gif') else 'png',
                            'roundNumber': round_number,
                            'size': item.get('size', 0)
                        })
            
            logger.info(f"✅ Found {len(overlays)} overlays for location: {location_name}")
            return overlays
            
        except Exception as e:
            logger.error(f"❌ Error fetching overlays for location {location_name}: {str(e)}")
            return []
    
    def _extract_round_number(self, filename: str) -> Optional[int]:
        """
        Extract round number from filename
        Supports patterns:
        - '01_Multiple Choice.png' -> 1
        - '02_Round 2.png' -> 2
        - 'round 3.png' -> 3
        - 'Round_4.gif' -> 4
        """
        # First try: Look for number prefix (e.g., "01_", "02_", "03_")
        prefix_match = re.match(r'^0*(\d+)_', filename)
        if prefix_match:
            return int(prefix_match.group(1))
        
        # Second try: Look for "round X" pattern
        round_match = re.search(r'round[\s_-]?(\d+)', filename.lower())
        if round_match:
            return int(round_match.group(1))
        
        return None
    
    def find_overlay_for_round(self, overlays: List[Dict], round_number: int, round_type: str) -> Optional[Dict]:
        """
        Find the appropriate overlay for a specific round
        
        Args:
            overlays: List of available overlays
            round_number: Round number (1-6)
            round_type: Type of round (MC, REG, MISC, MYS, BIG)
            
        Returns:
            Overlay dict or None
        """
        # Strategy 1: Find by exact round number match (highest priority)
        for overlay in overlays:
            if overlay.get('roundNumber') == round_number:
                logger.info(f"✅ Found exact round number match: {overlay['name']} for Round {round_number}")
                return overlay
        
        # Strategy 2: Match by round type in filename
        round_type_patterns = {
            'MC': ['multiple choice', 'mc', 'multiplechoice'],
            'MYS': ['mystery', 'mys'],
            'BIG': ['big', 'big question'],
            'REG': ['regular', 'reg'],
            'MISC': ['misc', 'miscellaneous']
        }
        
        if round_type in round_type_patterns:
            for pattern in round_type_patterns[round_type]:
                for overlay in overlays:
                    overlay_name = overlay['name'].lower()
                    if pattern in overlay_name:
                        logger.info(f"✅ Found round type match: {overlay['name']} for Round {round_number} ({round_type})")
                        return overlay
        
        # Strategy 3: Match by "round X" pattern in filename
        patterns = [
            f"round{round_number}",
            f"round_{round_number}",
            f"round {round_number}",
            f"r{round_number}"
        ]
        
        for overlay in overlays:
            overlay_name = overlay['name'].lower()
            for pattern in patterns:
                if pattern in overlay_name:
                    logger.info(f"✅ Found pattern match: {overlay['name']} for Round {round_number}")
                    return overlay
        
        logger.warning(f"⚠️ No overlay found for Round {round_number} ({round_type})")
        return None
    
    def apply_overlay_to_slide(self, slide: dict, overlay: Dict) -> dict:
        """
        Apply overlay reference to a slide
        
        Args:
            slide: Slide dictionary
            overlay: Overlay information dict
            
        Returns:
            Updated slide dictionary with overlay applied
        """
        # Add overlay information to slide metadata
        if 'metadata' not in slide:
            slide['metadata'] = {}
        
        slide['metadata']['overlayPath'] = overlay['path']
        slide['metadata']['overlayName'] = overlay['name']
        slide['metadata']['overlayType'] = overlay['type']
        
        # Download overlay and convert to base64 data URL
        overlay_data_url = self.get_overlay_as_data_url(overlay['path'], overlay['type'])
        
        if not overlay_data_url:
            logger.warning(f"⚠️ Could not load overlay image: {overlay['name']}")
            return slide
        
        # Remove any existing overlay elements (zIndex 1000) to prevent duplicates
        slide['elements'] = [e for e in slide.get('elements', []) if e.get('zIndex') != 1000]
        
        # Add overlay as an image element (top-most layer)
        overlay_element = {
            'type': 'image',
            'src': overlay_data_url,  # Base64 data URL
            'x': 0,
            'y': 0,
            'width': 1920,
            'height': 1080,
            'zIndex': 1000  # Ensure overlay is on top
        }
        
        slide['elements'].append(overlay_element)
        
        logger.info(f"✓ Applied overlay {overlay['name']} to slide (base64 embedded)")
        
        return slide
    
    def get_overlay_as_data_url(self, overlay_path: str, overlay_type: str) -> str:
        """
        Download overlay image and convert to base64 data URL.
        Uses in-memory cache to avoid re-downloading the same overlay.
        
        Args:
            overlay_path: SharePoint path to overlay file
            overlay_type: Type of overlay ('png' or 'gif')
            
        Returns:
            Base64 data URL string or empty string on failure
        """
        import base64
        
        # Check cache first
        cache_key = overlay_path
        if cache_key in self._overlay_cache:
            logger.info(f"📦 Using cached overlay: {overlay_path.split('/')[-1]}")
            return self._overlay_cache[cache_key]
        
        try:
            # Download the overlay file as bytes
            overlay_bytes = self.sp.download_file_to_bytes(overlay_path)
            
            if not overlay_bytes:
                logger.error(f"Failed to download overlay: {overlay_path}")
                return ""
            
            # Convert to base64
            base64_data = base64.b64encode(overlay_bytes).decode('utf-8')
            
            # Create data URL with appropriate MIME type
            mime_type = f"image/{overlay_type}"
            data_url = f"data:{mime_type};base64,{base64_data}"
            
            # Cache the result
            self._overlay_cache[cache_key] = data_url
            
            logger.info(f"✅ Downloaded & cached overlay ({len(overlay_bytes) / 1024:.1f}KB): {overlay_path.split('/')[-1]}")
            
            return data_url
            
        except Exception as e:
            logger.error(f"Error converting overlay to data URL: {str(e)}")
            return ""
    
    def get_overlay_url(self, overlay_path: str) -> str:
        """
        Get SharePoint URL for overlay image
        
        Args:
            overlay_path: SharePoint path to overlay file
            
        Returns:
            Direct URL to overlay image
        """
        try:
            url = self.sp.get_file_url(overlay_path)
            return url
        except Exception as e:
            logger.error(f"Error getting overlay URL for {overlay_path}: {str(e)}")
            return ""
    
    def find_overlay_by_name(self, overlays: List[Dict], name: str) -> Optional[Dict]:
        """
        Find overlay by name match (e.g., 'Answers' or 'Answer')
        Handles both singular and plural variations
        """
        # Remove trailing 's' for flexible matching (Answers -> Answer)
        name_base = name.rstrip('s').lower()
        
        for overlay in overlays:
            overlay_name = overlay['name'].lower()
            # Check if base name is in overlay filename
            if name_base in overlay_name:
                return overlay
        
        return None
    
    def get_overlay_applications(self, round_type: str, title_slide_idx: int, 
                                 round_overlay: Optional[Dict], answer_overlay: Optional[Dict]) -> List[Dict]:
        """
        Get list of overlay applications for a round based on specific rules.
        
        Returns list of: [{'slideIndex': int, 'overlay': dict}, ...]
        """
        applications = []
        
        if round_type == 'MC':
            # MC: Slides 2-11 (questions), slide 14 (answer)
            if round_overlay:
                for i in range(1, 11):  # Slides 2-11
                    applications.append({
                        'slideIndex': title_slide_idx + i,
                        'overlay': round_overlay
                    })
            if answer_overlay:
                applications.append({
                    'slideIndex': title_slide_idx + 13,  # Slide 14
                    'overlay': answer_overlay
                })
        
        elif round_type in ['REG', 'MISC']:
            # REG/MISC: Slides 2-11 (questions), slide 14 (answer)
            if round_overlay:
                for i in range(1, 11):  # Slides 2-11
                    applications.append({
                        'slideIndex': title_slide_idx + i,
                        'overlay': round_overlay
                    })
            if answer_overlay:
                applications.append({
                    'slideIndex': title_slide_idx + 13,  # Slide 14
                    'overlay': answer_overlay
                })
        
        elif round_type == 'MYS':
            # Mystery: Slides 2-10 (questions), slide 13 (answer)
            if round_overlay:
                for i in range(1, 10):  # Slides 2-10
                    applications.append({
                        'slideIndex': title_slide_idx + i,
                        'overlay': round_overlay
                    })
            if answer_overlay:
                applications.append({
                    'slideIndex': title_slide_idx + 12,  # Slide 13
                    'overlay': answer_overlay
                })
        
        elif round_type == 'BIG':
            # BIG: Slide 2, slides 4-7
            if round_overlay:
                applications.append({
                    'slideIndex': title_slide_idx + 1,  # Slide 2
                    'overlay': round_overlay
                })
                for i in range(3, 7):  # Slides 4-7
                    applications.append({
                        'slideIndex': title_slide_idx + i,
                        'overlay': round_overlay
                    })
        
        return applications
