"""
Story Generator Service - Creates MP4 videos for Instagram stories from trivia presentations.

Output: 25-second MP4 video with:
- Location image (5 seconds)
- Host GIF (5 seconds)  
- Background image with rounds layout (15 seconds)

Round colors:
- Green: Multiple Choice (MC) - always first
- Red: REG (General)
- Blue: MISC (Specific)
- Purple: Mystery (MYS)
- Yellow: BIG Question - always last

SharePoint folder structure (01_Socials):
- 01_Locations - Location images (named to match location)
- 02_Hosts - Host GIF files (named to match host)
- 03_Backgrounds - Background images (named to match location)
"""

import os
import uuid
import logging
import re
import io
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageSequence
import tempfile
import shutil

logger = logging.getLogger(__name__)

# Round type to color mapping
ROUND_COLORS = {
    'MC': '#22C55E',      # Green - Multiple Choice
    'REG': '#EF4444',     # Red - General
    'MISC': '#3B82F6',    # Blue - Specific
    'MYS': '#A855F7',     # Purple - Mystery
    'BIG': '#FFC107'      # Yellow - BIG Question
}

ROUND_DISPLAY_NAMES = {
    'MC': 'Multiple Choice',
    'REG': 'General',
    'MISC': 'Specific',
    'MYS': 'Mystery',
    'BIG': 'BIG Question'
}

# Canvas size for Instagram Stories (9:16 aspect ratio)
STORY_WIDTH = 1080
STORY_HEIGHT = 1920

# Base path for local assets (fallback)
ASSETS_DIR = Path(__file__).parent / 'assets'

# SharePoint folder path for social media assets
SHAREPOINT_SOCIALS_BASE = '01_Trivia/Web App/01_Socials'


class StoryGeneratorService:
    def __init__(self):
        self.locations_dir = ASSETS_DIR / 'locations'
        self.hosts_dir = ASSETS_DIR / 'hosts'
        self.backgrounds_dir = ASSETS_DIR / 'backgrounds'
        self.generated_dir = ASSETS_DIR / 'generated'
        self._sharepoint_service = None
        
        # SharePoint folder paths
        self.sp_locations_folder = f'{SHAREPOINT_SOCIALS_BASE}/01_Locations'
        self.sp_hosts_folder = f'{SHAREPOINT_SOCIALS_BASE}/02_Hosts'
        self.sp_backgrounds_folder = f'{SHAREPOINT_SOCIALS_BASE}/03_Backgrounds'
        
        # Cache for SharePoint assets
        self._sp_assets_cache = {
            'locations': None,
            'hosts': None,
            'backgrounds': None
        }
        
        # Ensure local directories exist (for fallback and generated files)
        for directory in [self.locations_dir, self.hosts_dir, self.backgrounds_dir, self.generated_dir]:
            directory.mkdir(parents=True, exist_ok=True)
    
    @property
    def sharepoint_service(self):
        """Lazy load SharePoint service"""
        if self._sharepoint_service is None:
            try:
                from sharepoint_service import SharePointService
                self._sharepoint_service = SharePointService()
                logger.info("SharePoint service initialized successfully")
            except Exception as e:
                logger.warning(f"Could not initialize SharePoint service: {e}. Using local assets only.")
                self._sharepoint_service = False  # Mark as unavailable
        return self._sharepoint_service if self._sharepoint_service else None
    
    def _list_sharepoint_folder(self, folder_path: str) -> List[Dict]:
        """List files in a SharePoint folder"""
        if not self.sharepoint_service:
            return []
        try:
            items = self.sharepoint_service.list_folder_contents(folder_path)
            return [item for item in items if 'file' in item]  # Filter to files only
        except Exception as e:
            logger.error(f"Error listing SharePoint folder {folder_path}: {e}")
            return []
    
    def _download_sharepoint_file(self, file_path: str) -> Optional[bytes]:
        """Download a file from SharePoint as bytes"""
        if not self.sharepoint_service:
            return None
        try:
            return self.sharepoint_service.download_file_to_bytes(file_path)
        except Exception as e:
            logger.error(f"Error downloading SharePoint file {file_path}: {e}")
            return None
    
    def _get_sharepoint_assets(self, asset_type: str) -> List[Dict]:
        """Get assets from SharePoint folder"""
        folder_map = {
            'locations': self.sp_locations_folder,
            'hosts': self.sp_hosts_folder,
            'backgrounds': self.sp_backgrounds_folder
        }
        
        folder_path = folder_map.get(asset_type)
        if not folder_path:
            return []
        
        # Check cache first (cache is cleared on refresh or after timeout)
        if self._sp_assets_cache.get(asset_type) is not None:
            return self._sp_assets_cache[asset_type]
        
        assets = []
        files = self._list_sharepoint_folder(folder_path)
        
        for file_info in files:
            filename = file_info.get('name', '')
            file_ext = Path(filename).suffix.lower()
            
            # Filter valid image/gif files
            if file_ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
                stem = Path(filename).stem
                # Remove numeric prefix (e.g., "01_" or "1_")
                clean_name = re.sub(r'^\d+_', '', stem)
                
                assets.append({
                    'id': stem,
                    'name': clean_name.replace('_', ' ').title(),
                    'path': f"{folder_path}/{filename}",
                    'type': 'gif' if file_ext == '.gif' else 'image',
                    'source': 'sharepoint'
                })
        
        # Cache the results
        self._sp_assets_cache[asset_type] = assets
        logger.info(f"Loaded {len(assets)} {asset_type} assets from SharePoint")
        return assets
    
    def refresh_sharepoint_cache(self):
        """Clear SharePoint asset cache to fetch fresh data"""
        self._sp_assets_cache = {
            'locations': None,
            'hosts': None,
            'backgrounds': None
        }
        logger.info("SharePoint asset cache cleared")
    
    def get_available_assets(self) -> Dict:
        """Get list of available assets from SharePoint and local storage"""
        locations = []
        hosts = []
        backgrounds = []
        
        # First, get SharePoint assets
        sp_locations = self._get_sharepoint_assets('locations')
        sp_hosts = self._get_sharepoint_assets('hosts')
        sp_backgrounds = self._get_sharepoint_assets('backgrounds')
        
        locations.extend(sp_locations)
        hosts.extend(sp_hosts)
        backgrounds.extend(sp_backgrounds)
        
        # Then, scan local directories (as fallback/additional)
        if self.locations_dir.exists():
            for f in self.locations_dir.iterdir():
                if f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
                    name = f.stem.replace('_', ' ').title()
                    # Only add if not already from SharePoint
                    if not any(a['id'].lower() == f.stem.lower() for a in locations):
                        locations.append({
                            'id': f.stem,
                            'name': name,
                            'path': str(f),
                            'type': 'image',
                            'source': 'local'
                        })
        
        if self.hosts_dir.exists():
            for f in self.hosts_dir.iterdir():
                if f.suffix.lower() in ['.gif', '.png', '.jpg', '.jpeg', '.webp']:
                    name = f.stem.replace('_', ' ').title()
                    if not any(a['id'].lower() == f.stem.lower() for a in hosts):
                        hosts.append({
                            'id': f.stem,
                            'name': name,
                            'path': str(f),
                            'type': 'gif' if f.suffix.lower() == '.gif' else 'image',
                            'source': 'local'
                        })
        
        if self.backgrounds_dir.exists():
            for f in self.backgrounds_dir.iterdir():
                if f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
                    name = f.stem.replace('_', ' ').title()
                    if not any(a['id'].lower() == f.stem.lower() for a in backgrounds):
                        backgrounds.append({
                            'id': f.stem,
                            'name': name,
                            'path': str(f),
                            'type': 'image',
                            'source': 'local'
                        })
        
        return {
            'locations': locations,
            'hosts': hosts,
            'backgrounds': backgrounds,
            'sharepoint_enabled': self.sharepoint_service is not None
        }
    
    def _normalize_location_name(self, location_path: str) -> str:
        """Extract clean location name from SharePoint path"""
        # Path like: 01_Trivia/Web App/00_Builder/02_Locations/01_Monkey Pants
        parts = location_path.split('/')
        if parts:
            # Get last part and remove numeric prefix
            name = parts[-1]
            # Remove prefix like "01_", "02_", etc.
            clean_name = re.sub(r'^\d+_', '', name)
            return clean_name.replace(' ', '_').lower()
        return 'unknown'
    
    def _normalize_host_name(self, host_path: str) -> str:
        """Extract clean host name from SharePoint path"""
        # Path like: 01_Trivia/Web App/00_Builder/01_Hosts/John Smith.pptx
        parts = host_path.split('/')
        if parts:
            name = parts[-1]
            # Remove .pptx extension
            name = name.replace('.pptx', '')
            # Remove numeric prefix
            clean_name = re.sub(r'^\d+_', '', name)
            return clean_name.replace(' ', '_').lower()
        return 'unknown'
    
    def _find_asset_local(self, asset_dir: Path, name: str, extensions: List[str]) -> Optional[Path]:
        """Find an asset file locally by name (case-insensitive)"""
        name_lower = name.lower()
        for ext in extensions:
            # Try exact match
            candidate = asset_dir / f"{name}{ext}"
            if candidate.exists():
                return candidate
            
            # Try case-insensitive match
            if asset_dir.exists():
                for f in asset_dir.iterdir():
                    if f.stem.lower() == name_lower and f.suffix.lower() == ext.lower():
                        return f
                    # Also try partial match (e.g., "monkey_pants" matches "01_Monkey_Pants")
                    clean_stem = re.sub(r'^\d+_', '', f.stem).lower().replace(' ', '_')
                    if clean_stem == name_lower and f.suffix.lower() == ext.lower():
                        return f
        
        return None
    
    def _find_sharepoint_asset(self, asset_type: str, name: str, extensions: List[str]) -> Optional[str]:
        """Find an asset in SharePoint by name"""
        assets = self._get_sharepoint_assets(asset_type)
        name_lower = name.lower().replace(' ', '_')
        
        for asset in assets:
            asset_name_clean = re.sub(r'^\d+_', '', asset['id']).lower().replace(' ', '_')
            asset_ext = Path(asset['path']).suffix.lower()
            
            # Match by name and extension
            if asset_name_clean == name_lower and asset_ext in extensions:
                return asset['path']
            
            # Also try partial/fuzzy match
            if name_lower in asset_name_clean or asset_name_clean in name_lower:
                if asset_ext in extensions:
                    return asset['path']
        
        return None
    
    def _load_image_from_sharepoint(self, sp_path: str) -> Optional[Image.Image]:
        """Download and load an image from SharePoint"""
        content = self._download_sharepoint_file(sp_path)
        if content:
            try:
                return Image.open(io.BytesIO(content))
            except Exception as e:
                logger.error(f"Error opening SharePoint image {sp_path}: {e}")
        return None
    
    def _get_location_image(self, location_name: str) -> Optional[Image.Image]:
        """Get location image from SharePoint or local storage"""
        extensions = ['.png', '.jpg', '.jpeg', '.webp']
        
        # Try SharePoint first
        sp_path = self._find_sharepoint_asset('locations', location_name, extensions)
        if sp_path:
            logger.info(f"Found location image in SharePoint: {sp_path}")
            img = self._load_image_from_sharepoint(sp_path)
            if img:
                return img
        
        # Fall back to local
        local_path = self._find_asset_local(self.locations_dir, location_name, extensions)
        if local_path:
            logger.info(f"Found location image locally: {local_path}")
            return Image.open(local_path)
        
        return None
    
    def _get_host_image(self, host_name: str) -> Tuple[Optional[Image.Image], bool]:
        """
        Get host image/GIF from SharePoint or local storage.
        Returns (image, is_gif) tuple.
        """
        extensions = ['.gif', '.png', '.jpg', '.jpeg', '.webp']
        
        # Try SharePoint first
        sp_path = self._find_sharepoint_asset('hosts', host_name, extensions)
        if sp_path:
            logger.info(f"Found host image in SharePoint: {sp_path}")
            content = self._download_sharepoint_file(sp_path)
            if content:
                try:
                    img = Image.open(io.BytesIO(content))
                    is_gif = sp_path.lower().endswith('.gif')
                    return img, is_gif
                except Exception as e:
                    logger.error(f"Error opening SharePoint host image: {e}")
        
        # Fall back to local
        local_path = self._find_asset_local(self.hosts_dir, host_name, extensions)
        if local_path:
            logger.info(f"Found host image locally: {local_path}")
            return Image.open(local_path), local_path.suffix.lower() == '.gif'
        
        return None, False
    
    def _get_background_image(self, location_name: str) -> Optional[Image.Image]:
        """Get background image from SharePoint or local storage"""
        extensions = ['.png', '.jpg', '.jpeg', '.webp']
        
        # Try SharePoint first
        sp_path = self._find_sharepoint_asset('backgrounds', location_name, extensions)
        if sp_path:
            logger.info(f"Found background image in SharePoint: {sp_path}")
            img = self._load_image_from_sharepoint(sp_path)
            if img:
                return img
        
        # Fall back to local
        local_path = self._find_asset_local(self.backgrounds_dir, location_name, extensions)
        if local_path:
            logger.info(f"Found background image locally: {local_path}")
            return Image.open(local_path)
        
        return None
    
    def _create_placeholder_image(self, width: int, height: int, text: str, bg_color: str = '#333333') -> Image.Image:
        """Create a placeholder image with text"""
        img = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(img)
        
        # Try to use a nice font, fall back to default
        try:
            font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 48)
        except (IOError, OSError):
            font = ImageFont.load_default()
        
        # Calculate text position
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        
        draw.text((x, y), text, fill='white', font=font)
        return img
    
    def _resize_to_story(self, img: Image.Image) -> Image.Image:
        """Resize and crop image to fit story dimensions (9:16)"""
        # Calculate aspect ratios
        img_ratio = img.width / img.height
        story_ratio = STORY_WIDTH / STORY_HEIGHT
        
        if img_ratio > story_ratio:
            # Image is wider - crop width
            new_height = STORY_HEIGHT
            new_width = int(new_height * img_ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            # Crop center
            left = (new_width - STORY_WIDTH) // 2
            img = img.crop((left, 0, left + STORY_WIDTH, STORY_HEIGHT))
        else:
            # Image is taller - crop height
            new_width = STORY_WIDTH
            new_height = int(new_width / img_ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            # Crop center
            top = (new_height - STORY_HEIGHT) // 2
            img = img.crop((0, top, STORY_WIDTH, top + STORY_HEIGHT))
        
        return img
    
    def _create_rounds_overlay(self, rounds_info: List[Dict], location_name: str) -> Image.Image:
        """
        Create the rounds layout overlay image matching the reference design.
        
        Layout order (top to bottom):
        1. Green "Multiple Choice" box (static - always first, no dynamic text needed)
        2. Red (REG) boxes - with round names
        3. Blue (MISC) boxes - with round names
        4. Purple "Mystery" box (static)
        5. Yellow "BIG Question" section - with the BIG question round name
        """
        # Create transparent overlay
        overlay = Image.new('RGBA', (STORY_WIDTH, STORY_HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Try to load fonts
        try:
            title_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 56)
            round_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 32)
            big_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 48)
            small_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 24)
        except (IOError, OSError):
            title_font = ImageFont.load_default()
            round_font = ImageFont.load_default()
            big_font = ImageFont.load_default()
            small_font = ImageFont.load_default()
        
        # Draw semi-transparent dark overlay for better readability
        draw.rectangle([(0, 300), (STORY_WIDTH, STORY_HEIGHT - 100)], 
                      fill=(0, 0, 0, 160), outline=None)
        
        # Draw location name at top
        loc_text = location_name.replace('_', ' ').upper()
        bbox = draw.textbbox((0, 0), loc_text, font=title_font)
        loc_x = (STORY_WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((loc_x, 350), loc_text, fill='#FFC107', font=title_font)
        
        # Separate rounds by type for correct ordering
        # MC and MYS are static elements, so we don't need to extract them
        reg_rounds = [r for r in rounds_info if r.get('type') == 'REG']
        misc_rounds = [r for r in rounds_info if r.get('type') == 'MISC']
        big_rounds = [r for r in rounds_info if r.get('type') == 'BIG']
        
        # Layout parameters
        bar_height = 65
        bar_spacing = 15
        bar_margin = 60
        y_start = 480
        current_y = y_start
        
        # 1. GREEN "Multiple Choice" box (static - always shows "Multiple Choice")
        x1, x2 = bar_margin, STORY_WIDTH - bar_margin
        draw.rounded_rectangle(
            [(x1, current_y), (x2, current_y + bar_height)],
            radius=15,
            fill='#22C55E'  # Green
        )
        # Center the text "Multiple Choice"
        mc_text = "Multiple Choice"
        bbox = draw.textbbox((0, 0), mc_text, font=round_font)
        text_x = (STORY_WIDTH - (bbox[2] - bbox[0])) // 2
        text_y = current_y + (bar_height - (bbox[3] - bbox[1])) // 2
        draw.text((text_x, text_y), mc_text, fill='white', font=round_font)
        current_y += bar_height + bar_spacing
        
        # 2. RED (REG) boxes - with round names
        for reg_round in reg_rounds:
            round_name = reg_round.get('name', 'General')
            draw.rounded_rectangle(
                [(x1, current_y), (x2, current_y + bar_height)],
                radius=15,
                fill='#EF4444'  # Red
            )
            # Center the round name
            bbox = draw.textbbox((0, 0), round_name, font=round_font)
            text_x = (STORY_WIDTH - (bbox[2] - bbox[0])) // 2
            text_y = current_y + (bar_height - (bbox[3] - bbox[1])) // 2
            draw.text((text_x, text_y), round_name, fill='white', font=round_font)
            current_y += bar_height + bar_spacing
        
        # 3. BLUE (MISC) boxes - with round names
        for misc_round in misc_rounds:
            round_name = misc_round.get('name', 'Specific')
            draw.rounded_rectangle(
                [(x1, current_y), (x2, current_y + bar_height)],
                radius=15,
                fill='#3B82F6'  # Blue
            )
            # Center the round name
            bbox = draw.textbbox((0, 0), round_name, font=round_font)
            text_x = (STORY_WIDTH - (bbox[2] - bbox[0])) // 2
            text_y = current_y + (bar_height - (bbox[3] - bbox[1])) // 2
            draw.text((text_x, text_y), round_name, fill='white', font=round_font)
            current_y += bar_height + bar_spacing
        
        # 4. PURPLE "Mystery" box (static)
        draw.rounded_rectangle(
            [(x1, current_y), (x2, current_y + bar_height)],
            radius=15,
            fill='#A855F7'  # Purple
        )
        mystery_text = "Mystery"
        bbox = draw.textbbox((0, 0), mystery_text, font=round_font)
        text_x = (STORY_WIDTH - (bbox[2] - bbox[0])) // 2
        text_y = current_y + (bar_height - (bbox[3] - bbox[1])) // 2
        draw.text((text_x, text_y), mystery_text, fill='white', font=round_font)
        current_y += bar_height + bar_spacing + 10  # Extra spacing before BIG
        
        # 5. YELLOW "BIG Question" section
        # Draw "BIG" text
        big_text = "BIG"
        bbox = draw.textbbox((0, 0), big_text, font=big_font)
        big_x = (STORY_WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((big_x, current_y), big_text, fill='#FFC107', font=big_font)
        current_y += 55
        
        # Draw "Question:" label
        question_label = "Question:"
        bbox = draw.textbbox((0, 0), question_label, font=small_font)
        q_x = (STORY_WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((q_x, current_y), question_label, fill='#FFD54F', font=small_font)
        current_y += 35
        
        # Draw yellow box with BIG round name
        big_name = big_rounds[0].get('name', 'Final Question') if big_rounds else 'Final Question'
        draw.rounded_rectangle(
            [(x1, current_y), (x2, current_y + bar_height)],
            radius=15,
            fill='#FFC107'  # Yellow
        )
        bbox = draw.textbbox((0, 0), big_name, font=round_font)
        text_x = (STORY_WIDTH - (bbox[2] - bbox[0])) // 2
        text_y = current_y + (bar_height - (bbox[3] - bbox[1])) // 2
        draw.text((text_x, text_y), big_name, fill='black', font=round_font)
        
        return overlay
    
    def generate_story_frames(self, presentation_data: Dict) -> Tuple[List[Image.Image], List[float]]:
        """
        Generate story frames from presentation data.
        Returns list of frames and their durations.
        
        Fetches assets from SharePoint first, falls back to local storage.
        """
        frames = []
        durations = []
        
        location_name = self._normalize_location_name(presentation_data.get('location', ''))
        host_name = self._normalize_host_name(presentation_data.get('hostFile', ''))
        rounds_info = presentation_data.get('roundFiles', [])
        
        logger.info(f"Generating story for location: {location_name}, host: {host_name}")
        
        # 1. Location image (5 seconds) - from SharePoint or local
        location_img = self._get_location_image(location_name)
        if location_img:
            location_img = location_img.convert('RGB')
        else:
            # Create placeholder
            logger.warning(f"No location image found for {location_name}, using placeholder")
            location_img = self._create_placeholder_image(
                STORY_WIDTH, STORY_HEIGHT, 
                f"Location:\n{location_name.replace('_', ' ').title()}",
                '#1a1a2e'
            )
        location_img = self._resize_to_story(location_img)
        frames.append(location_img)
        durations.append(5.0)
        
        # 2. Host GIF/image (5 seconds) - from SharePoint or local
        host_img, is_gif = self._get_host_image(host_name)
        
        if host_img and is_gif:
            # Handle GIF - extract frames
            gif_frames = []
            try:
                for frame in ImageSequence.Iterator(host_img):
                    frame_rgb = frame.convert('RGB')
                    frame_rgb = self._resize_to_story(frame_rgb)
                    gif_frames.append(frame_rgb)
            except (IOError, OSError, ValueError) as e:
                logger.error(f"Error extracting GIF frames: {e}")
            
            if gif_frames:
                # Calculate frame duration for 5 seconds total
                frame_duration = 5.0 / len(gif_frames)
                for gf in gif_frames:
                    frames.append(gf)
                    durations.append(frame_duration)
            else:
                # Fallback to static image
                logger.warning(f"Could not extract GIF frames for host {host_name}")
                host_img_static = self._create_placeholder_image(
                    STORY_WIDTH, STORY_HEIGHT,
                    f"Host:\n{host_name.replace('_', ' ').title()}",
                    '#16213e'
                )
                frames.append(host_img_static)
                durations.append(5.0)
        elif host_img:
            # Static image
            host_img = host_img.convert('RGB')
            host_img = self._resize_to_story(host_img)
            frames.append(host_img)
            durations.append(5.0)
        else:
            # Create placeholder
            logger.warning(f"No host image found for {host_name}, using placeholder")
            host_img = self._create_placeholder_image(
                STORY_WIDTH, STORY_HEIGHT,
                f"Host:\n{host_name.replace('_', ' ').title()}",
                '#16213e'
            )
            frames.append(host_img)
            durations.append(5.0)
        
        # 3. Background with rounds (15 seconds) - from SharePoint or local
        bg_img = self._get_background_image(location_name)
        if bg_img:
            bg_img = bg_img.convert('RGBA')
        else:
            # Use a default dark background
            logger.warning(f"No background image found for {location_name}, using default")
            bg_img = Image.new('RGBA', (STORY_WIDTH, STORY_HEIGHT), (26, 26, 46, 255))
        
        bg_img = self._resize_to_story(bg_img.convert('RGB')).convert('RGBA')
        
        # Create rounds overlay
        rounds_overlay = self._create_rounds_overlay(rounds_info, location_name)
        
        # Composite
        final_bg = Image.alpha_composite(bg_img, rounds_overlay)
        frames.append(final_bg.convert('RGB'))
        durations.append(15.0)
        
        return frames, durations
    
    def generate_video(self, presentation_data: Dict, output_filename: Optional[str] = None) -> str:
        """
        Generate an MP4 video from presentation data.
        Returns path to the generated video.
        """
        try:
            # Try moviepy 2.x import first
            try:
                from moviepy import ImageClip, concatenate_videoclips
            except ImportError:
                # Fall back to moviepy 1.x import
                from moviepy.editor import ImageClip, concatenate_videoclips
        except ImportError:
            logger.error("moviepy not installed. Please install it with: pip install moviepy")
            raise ImportError("moviepy is required for video generation")
        
        # Generate frames
        frames, durations = self.generate_story_frames(presentation_data)
        
        if not frames:
            raise ValueError("No frames generated")
        
        # Create video clips
        clips = []
        temp_files = []
        
        try:
            for i, (frame, duration) in enumerate(zip(frames, durations)):
                # Save frame to temp file
                temp_path = self.generated_dir / f"temp_frame_{i}.png"
                frame.save(temp_path)
                temp_files.append(temp_path)
                
                # Create clip
                clip = ImageClip(str(temp_path)).with_duration(duration)
                clips.append(clip)
            
            # Concatenate clips
            final_clip = concatenate_videoclips(clips, method="compose")
            
            # Generate output filename
            if not output_filename:
                output_filename = f"story_{uuid.uuid4().hex[:8]}.mp4"
            
            output_path = self.generated_dir / output_filename
            
            # Write video with audio codec set (even though no audio)
            final_clip.write_videofile(
                str(output_path),
                fps=24,
                codec='libx264',
                audio=False,
                preset='ultrafast',
                threads=4
            )
            
            final_clip.close()
            
            return str(output_path)
        
        finally:
            # Cleanup temp files
            for temp_file in temp_files:
                try:
                    temp_file.unlink()
                except (IOError, OSError):
                    pass
    
    def upload_asset(self, file_content: bytes, filename: str, asset_type: str) -> Dict:
        """
        Upload an asset (location image, host gif, or background).
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            asset_type: 'location', 'host', or 'background'
        """
        # Determine target directory
        if asset_type == 'location':
            target_dir = self.locations_dir
        elif asset_type == 'host':
            target_dir = self.hosts_dir
        elif asset_type == 'background':
            target_dir = self.backgrounds_dir
        else:
            raise ValueError(f"Invalid asset type: {asset_type}")
        
        # Clean filename
        safe_filename = filename.replace(' ', '_').lower()
        target_path = target_dir / safe_filename
        
        # Write file
        with open(target_path, 'wb') as f:
            f.write(file_content)
        
        return {
            'id': target_path.stem,
            'name': target_path.stem.replace('_', ' ').title(),
            'path': str(target_path),
            'type': 'gif' if target_path.suffix.lower() == '.gif' else 'image'
        }
    
    def delete_asset(self, asset_id: str, asset_type: str) -> bool:
        """
        Delete an asset.
        
        Args:
            asset_id: Asset ID (filename without extension)
            asset_type: 'location', 'host', or 'background'
        """
        if asset_type == 'location':
            target_dir = self.locations_dir
        elif asset_type == 'host':
            target_dir = self.hosts_dir
        elif asset_type == 'background':
            target_dir = self.backgrounds_dir
        else:
            raise ValueError(f"Invalid asset type: {asset_type}")
        
        # Find and delete file
        for f in target_dir.iterdir():
            if f.stem.lower() == asset_id.lower():
                f.unlink()
                return True
        
        return False


# Singleton instance
_story_service = None

def get_story_service() -> StoryGeneratorService:
    global _story_service
    if _story_service is None:
        _story_service = StoryGeneratorService()
    return _story_service
