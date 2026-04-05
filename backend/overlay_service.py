"""
Overlay Service - Manages location-specific overlays for trivia presentations
Fetches PNG/GIF overlays from SharePoint and applies them to slides

Now uses Rust for fast base64 encoding of PNG and GIF images (when available)

Memory Optimization Features:
- LRU cache with configurable max size (default 100MB)
- Automatic eviction of oldest entries when limit exceeded
- Memory usage tracking and reporting
"""
import logging
import time
from typing import List, Dict, Optional
from collections import OrderedDict
from sharepoint_service import SharePointService
import re
import os

logger = logging.getLogger(__name__)

# Memory configuration (can be overridden via environment)
# OPTIMIZATION: Reduced default cache size for production (50MB instead of 100MB)
MAX_CACHE_SIZE_MB = int(os.environ.get('OVERLAY_CACHE_MAX_MB', '50'))  # Default 50MB for production
MAX_CACHE_SIZE_BYTES = MAX_CACHE_SIZE_MB * 1024 * 1024

# Try to import the Rust overlay processor for faster image processing
try:
    import pptx_parser
    RUST_OVERLAY_AVAILABLE = True
    logger.info("✅ Rust overlay processor available - using fast native encoding")
except ImportError:
    RUST_OVERLAY_AVAILABLE = False
    logger.warning("⚠️ Rust overlay processor not available - falling back to Python")


class LRUOverlayCache:
    """
    Memory-efficient LRU cache for overlay images with size limits.
    Automatically evicts oldest entries when max size is exceeded.
    """
    
    def __init__(self, max_size_bytes: int = MAX_CACHE_SIZE_BYTES):
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._sizes: Dict[str, int] = {}  # Track individual item sizes
        self._current_size = 0
        self._max_size = max_size_bytes
        self._hits = 0
        self._misses = 0
        self._evictions = 0
    
    def get(self, key: str) -> Optional[str]:
        """Get item from cache, moving it to end (most recently used)"""
        if key in self._cache:
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None
    
    def set(self, key: str, value: str) -> None:
        """Add item to cache, evicting oldest if necessary"""
        value_size = len(value)
        
        # If single item exceeds max, don't cache it
        if value_size > self._max_size:
            logger.warning(f"⚠️ Overlay too large to cache ({value_size/1024/1024:.1f}MB > {self._max_size/1024/1024:.1f}MB): {key.split('/')[-1]}")
            return
        
        # Remove existing entry if updating
        if key in self._cache:
            self._current_size -= self._sizes[key]
            del self._cache[key]
            del self._sizes[key]
        
        # Evict oldest entries until we have space
        while self._current_size + value_size > self._max_size and self._cache:
            oldest_key, oldest_value = self._cache.popitem(last=False)
            self._current_size -= self._sizes.pop(oldest_key)
            self._evictions += 1
            logger.debug(f"🗑️ Evicted from cache: {oldest_key.split('/')[-1]}")
        
        # Add new entry
        self._cache[key] = value
        self._sizes[key] = value_size
        self._current_size += value_size
    
    def __contains__(self, key: str) -> bool:
        return key in self._cache
    
    def __len__(self) -> int:
        return len(self._cache)
    
    def clear(self) -> None:
        """Clear all cached items"""
        self._cache.clear()
        self._sizes.clear()
        self._current_size = 0
    
    def get_stats(self) -> dict:
        """Get cache statistics"""
        return {
            'items': len(self._cache),
            'size_mb': self._current_size / 1024 / 1024,
            'max_size_mb': self._max_size / 1024 / 1024,
            'utilization_pct': (self._current_size / self._max_size * 100) if self._max_size > 0 else 0,
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate_pct': (self._hits / (self._hits + self._misses) * 100) if (self._hits + self._misses) > 0 else 0,
            'evictions': self._evictions,
        }


# Global LRU cache for overlay images (persists across requests)
_overlay_image_cache = LRUOverlayCache()

# Global Rust processor instance (reuse for caching benefits)
_rust_overlay_processor = None

def get_rust_overlay_processor():
    """Get or create the global Rust overlay processor instance"""
    global _rust_overlay_processor
    if _rust_overlay_processor is None and RUST_OVERLAY_AVAILABLE:
        _rust_overlay_processor = pptx_parser.RustOverlayProcessor()
        logger.info("🦀 Created Rust overlay processor instance")
    return _rust_overlay_processor

def clear_overlay_caches():
    """Clear both Python and Rust overlay caches to free memory"""
    global _overlay_image_cache, _rust_overlay_processor
    _overlay_image_cache.clear()
    if _rust_overlay_processor:
        _rust_overlay_processor.clear_cache()
    logger.info("🧹 Cleared all overlay caches")


class OverlayService:
    """Service for managing presentation overlays with memory-efficient caching"""
    
    def __init__(self, use_rust: bool = True):
        self.sp = SharePointService()
        # Use global LRU cache so it persists across requests
        self._overlay_cache = _overlay_image_cache
        # Use Rust processor if available and enabled
        self.use_rust = use_rust and RUST_OVERLAY_AVAILABLE
        self.rust_processor = get_rust_overlay_processor() if self.use_rust else None
        self._rust_time = 0.0
        self._python_time = 0.0
    
    def get_location_overlays(self, location_name: str) -> List[Dict[str, str]]:
        """
        Get all available overlays for a specific location
        
        Args:
            location_name: Name of the location (e.g., "Monkey Pants", "Crooked Pint")
            
        Returns:
            List of overlay files with metadata
        """
        try:
            # First, find the actual folder name (may have numeric prefix like "01_Monkey Pants")
            base_path = "01_Trivia/Web App/00_Builder/02_Locations"
            
            # List all location folders to find the matching one
            location_folders = self.sp.list_folder_contents(base_path)
            
            actual_folder_name = None
            location_name_lower = location_name.lower().strip()
            
            for folder in location_folders:
                if folder.get('folder'):
                    folder_name = folder['name']
                    # Match exact name or name without numeric prefix (e.g., "01_Monkey Pants" -> "Monkey Pants")
                    folder_name_clean = folder_name.lower().strip()
                    # Remove numeric prefix if present (e.g., "01_", "02_", etc.)
                    import re
                    folder_name_without_prefix = re.sub(r'^\d+_', '', folder_name_clean)
                    
                    if folder_name_clean == location_name_lower or folder_name_without_prefix == location_name_lower:
                        actual_folder_name = folder['name']
                        break
            
            if not actual_folder_name:
                logger.warning(f"⚠️ Location folder not found for: {location_name}")
                return []
            
            overlay_folder = f"{base_path}/{actual_folder_name}"
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
            
            logger.info(f"✅ Found {len(overlays)} overlays for location: {location_name} (folder: {actual_folder_name})")
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
        Uses Rust for fast base64 encoding when available.
        Uses LRU cache with memory limits to avoid unbounded growth.
        
        Args:
            overlay_path: SharePoint path to overlay file
            overlay_type: Type of overlay ('png' or 'gif')
            
        Returns:
            Base64 data URL string or empty string on failure
        """
        # Check LRU cache first
        cache_key = overlay_path
        cached_value = self._overlay_cache.get(cache_key)
        if cached_value:
            logger.info(f"📦 Using cached overlay: {overlay_path.split('/')[-1]}")
            return cached_value
        
        try:
            start_time = time.time()
            
            # Download the overlay file as bytes
            overlay_bytes = self.sp.download_file_to_bytes(overlay_path)
            
            if not overlay_bytes:
                logger.error(f"Failed to download overlay: {overlay_path}")
                return ""
            
            download_time = time.time() - start_time
            logger.debug(f"Download took {download_time*1000:.1f}ms")
            
            # Use Rust processor if available for fast base64 encoding
            if self.use_rust and self.rust_processor:
                try:
                    rust_start = time.time()
                    result = self.rust_processor.process_overlay_bytes(
                        overlay_bytes, 
                        overlay_type,
                        cache_key  # Use cache_key for Rust-side caching too
                    )
                    data_url = result['dataUrl']
                    rust_time = time.time() - rust_start
                    self._rust_time += rust_time
                    
                    # Cache in LRU cache (will auto-evict if needed)
                    self._overlay_cache.set(cache_key, data_url)
                    
                    logger.info(f"🦀 Rust processed overlay ({len(overlay_bytes) / 1024:.1f}KB) in {rust_time*1000:.1f}ms: {overlay_path.split('/')[-1]}")
                    
                    return data_url
                except Exception as rust_err:
                    logger.warning(f"⚠️ Rust processing failed, falling back to Python: {rust_err}")
            
            # Python fallback for base64 encoding
            python_start = time.time()
            import base64
            
            base64_data = base64.b64encode(overlay_bytes).decode('utf-8')
            
            # Create data URL with appropriate MIME type
            mime_type = f"image/{overlay_type}"
            data_url = f"data:{mime_type};base64,{base64_data}"
            
            python_time = time.time() - python_start
            self._python_time += python_time
            
            # Cache in LRU cache (will auto-evict if needed)
            self._overlay_cache.set(cache_key, data_url)
            
            logger.info(f"🐍 Python processed overlay ({len(overlay_bytes) / 1024:.1f}KB) in {python_time*1000:.1f}ms: {overlay_path.split('/')[-1]}")
            
            return data_url
            
        except Exception as e:
            logger.error(f"Error converting overlay to data URL: {str(e)}")
            return ""
    
    def get_overlays_batch(self, overlay_items: List[Dict]) -> Dict[str, str]:
        """
        Process multiple overlays in parallel using Rayon batch processing.
        This is significantly faster when loading presentations with many overlays.
        
        Args:
            overlay_items: List of dicts with 'path' and 'type' keys
            
        Returns:
            Dict mapping cache_key (path) to data URL
        """
        if not overlay_items:
            return {}
        
        # Separate cached vs uncached items
        results = {}
        uncached_items = []
        
        for item in overlay_items:
            cache_key = item['path']
            cached_value = self._overlay_cache.get(cache_key)
            if cached_value:
                results[cache_key] = cached_value
                logger.debug(f"📦 Batch: Using cached overlay: {cache_key.split('/')[-1]}")
            else:
                uncached_items.append(item)
        
        if not uncached_items:
            logger.info(f"🚀 Batch: All {len(overlay_items)} overlays served from cache")
            return results
        
        # Download uncached overlays
        download_start = time.time()
        downloaded = []
        for item in uncached_items:
            try:
                overlay_bytes = self.sp.download_file_to_bytes(item['path'])
                if overlay_bytes:
                    downloaded.append({
                        'path': item['path'],
                        'type': item['type'],
                        'bytes': overlay_bytes
                    })
            except Exception as e:
                logger.warning(f"⚠️ Failed to download overlay {item['path']}: {e}")
        
        download_time = time.time() - download_start
        logger.info(f"📥 Batch: Downloaded {len(downloaded)} overlays in {download_time*1000:.1f}ms")
        
        if not downloaded:
            return results
        
        # Process with Rust batch processing if available
        if self.use_rust and self.rust_processor:
            try:
                rust_start = time.time()
                
                # Prepare batch items: [(bytes, image_type, cache_key), ...]
                batch_items = [
                    (item['bytes'], item['type'], item['path'])
                    for item in downloaded
                ]
                
                # Process in parallel
                batch_results = self.rust_processor.process_batch(batch_items)
                
                rust_time = time.time() - rust_start
                self._rust_time += rust_time
                
                # Extract results and cache with LRU
                for result in batch_results:
                    cache_key = result['cacheKey']
                    if result['success']:
                        data_url = result['data']['dataUrl']
                        results[cache_key] = data_url
                        self._overlay_cache.set(cache_key, data_url)
                    else:
                        logger.warning(f"⚠️ Batch: Failed to process {cache_key}: {result.get('error')}")
                
                total_size = sum(len(item['bytes']) for item in downloaded)
                logger.info(f"🦀 Batch: Rust processed {len(downloaded)} overlays ({total_size/1024:.1f}KB) in {rust_time*1000:.1f}ms")
                
                return results
                
            except Exception as rust_err:
                logger.warning(f"⚠️ Rust batch processing failed, falling back to Python: {rust_err}")
        
        # Python fallback (sequential)
        python_start = time.time()
        import base64
        
        for item in downloaded:
            try:
                cache_key = item['path']
                overlay_bytes = item['bytes']
                overlay_type = item['type']
                
                base64_data = base64.b64encode(overlay_bytes).decode('utf-8')
                mime_type = f"image/{overlay_type}"
                data_url = f"data:{mime_type};base64,{base64_data}"
                
                results[cache_key] = data_url
                self._overlay_cache.set(cache_key, data_url)
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to process overlay {item['path']}: {e}")
        
        python_time = time.time() - python_start
        self._python_time += python_time
        
        total_size = sum(len(item['bytes']) for item in downloaded)
        logger.info(f"🐍 Batch: Python processed {len(downloaded)} overlays ({total_size/1024:.1f}KB) in {python_time*1000:.1f}ms")
        
        return results
    
    def get_processing_stats(self) -> dict:
        """Get overlay processing statistics including LRU cache info"""
        # Get LRU cache stats
        cache_stats = self._overlay_cache.get_stats()
        
        stats = {
            'use_rust': self.use_rust,
            'rust_available': RUST_OVERLAY_AVAILABLE,
            'rust_time_ms': self._rust_time * 1000,
            'python_time_ms': self._python_time * 1000,
            # LRU cache stats
            'cache_items': cache_stats['items'],
            'cache_size_mb': round(cache_stats['size_mb'], 2),
            'cache_max_mb': cache_stats['max_size_mb'],
            'cache_utilization_pct': round(cache_stats['utilization_pct'], 1),
            'cache_hit_rate_pct': round(cache_stats['hit_rate_pct'], 1),
            'cache_evictions': cache_stats['evictions'],
        }
        if self.rust_processor:
            rust_stats = self.rust_processor.get_stats()
            stats['rust_images_processed'] = rust_stats.get('images_processed', 0)
            stats['rust_cache_hits'] = rust_stats.get('cache_hits', 0)
            stats['rust_cache_size'] = rust_stats.get('cache_size', 0)
            stats['rust_batch_processed'] = rust_stats.get('batch_processed', 0)
        return stats
    
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
