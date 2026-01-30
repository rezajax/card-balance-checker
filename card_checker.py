#!/usr/bin/env python3
"""
Card Balance Checker - اتومیشن چک بالانس کارت
استفاده از Playwright برای تعامل با rcbalance.com
با قابلیت تغییر Tailscale exit node برای دور زدن CAPTCHA
حالا با پشتیبانی از AI CAPTCHA Solver (vision-ai-recaptcha-solver)
"""

import asyncio
import subprocess
from playwright.async_api import async_playwright, Page, Browser
from datetime import datetime
import logging
import re
import random
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import AI CAPTCHA solver components
AI_SOLVER_AVAILABLE = False
YOLO_MODEL = None
YOLO_CLASSES = None
AI_MODEL_PRELOADED = False

try:
    import sys
    import os
    project_dir = os.path.dirname(os.path.abspath(__file__))
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    
    from ultralytics import YOLO
    import cv2
    import numpy as np
    from PIL import Image
    import io
    import base64
    import aiohttp
    from huggingface_hub import hf_hub_download
    
    # reCAPTCHA classification classes (from DannyLuna model)
    YOLO_CLASSES = {
        0: 'bicycle', 1: 'bridge', 2: 'bus', 3: 'car', 4: 'chimney',
        5: 'crosswalk', 6: 'fire hydrant', 7: 'motorcycle', 8: 'mountain',
        9: 'other', 10: 'palm tree', 11: 'stairs', 12: 'tractor', 13: 'traffic light'
    }
    
    # Mapping of challenge text to class IDs
    CHALLENGE_MAPPING = {
        'bicycle': [0],
        'bicycles': [0],
        'bike': [0],
        'bikes': [0],
        'bridge': [1],
        'bridges': [1],
        'bus': [2],
        'buses': [2],
        'car': [3],
        'cars': [3],
        'chimney': [4],
        'chimneys': [4],
        'crosswalk': [5],
        'crosswalks': [5],
        'cross walk': [5],
        'fire hydrant': [6],
        'fire hydrants': [6],
        'hydrant': [6],
        'hydrants': [6],
        'motorcycle': [7],
        'motorcycles': [7],
        'motorbike': [7],
        'motorbikes': [7],
        'mountain': [8],
        'mountains': [8],
        'palm tree': [10],
        'palm trees': [10],
        'palm': [10],
        'stair': [11],
        'stairs': [11],
        'staircase': [11],
        'tractor': [12],
        'tractors': [12],
        'traffic light': [13],
        'traffic lights': [13],
        'traffic signal': [13],
        'stop light': [13],
    }
    
    AI_SOLVER_AVAILABLE = True
    logger.info("AI CAPTCHA Solver components loaded successfully")
    
    # Pre-load the model at startup to avoid delays during CAPTCHA solving
    def preload_ai_model():
        """Pre-load the YOLO model at startup (only if captcha_mode is 'ai')"""
        global YOLO_MODEL, AI_MODEL_PRELOADED
        if YOLO_MODEL is not None:
            return True
        
        # Check settings to see if we should preload
        import json
        settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.json')
        try:
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                    captcha_mode = settings.get('captcha_mode', 'auto')
                    if captcha_mode != 'ai':
                        logger.info(f"[AI Solver] Skipping YOLO preload - captcha_mode is '{captcha_mode}' (not 'ai')")
                        return False
        except Exception as e:
            logger.warning(f"[AI Solver] Could not read settings: {e}")
        
        try:
            logger.info("[AI Solver] Pre-loading model at startup (first run downloads ~109MB)...")
            model_path = hf_hub_download(
                repo_id="DannyLuna/recaptcha-classification-57k",
                filename="recaptcha_classification_57k.onnx"
            )
            logger.info(f"[AI Solver] Model downloaded to: {model_path}")
            YOLO_MODEL = YOLO(model_path, task='classify')
            AI_MODEL_PRELOADED = True
            logger.info("[AI Solver] Model pre-loaded successfully! AI CAPTCHA solver is ready.")
            return True
        except Exception as e:
            logger.error(f"[AI Solver] Failed to pre-load model: {e}")
            return False
    
    # Try to preload the model (only if captcha_mode is 'ai')
    preload_ai_model()
    
except ImportError as e:
    logger.warning(f"AI CAPTCHA solver dependencies not available: {e}")
    logger.warning("AI mode will not be available. Install with: pip install ultralytics opencv-python aiohttp huggingface_hub")


class TailscaleManager:
    """Manager for Tailscale exit node switching"""
    
    @staticmethod
    def get_available_exit_nodes() -> list:
        """Get list of available online exit nodes"""
        try:
            result = subprocess.run(
                ['tailscale', 'status'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            exit_nodes = []
            for line in result.stdout.split('\n'):
                if 'offers exit node' in line and 'offline' not in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        ip = parts[0]
                        hostname = parts[1]
                        exit_nodes.append({
                            'ip': ip,
                            'hostname': hostname,
                            'active': 'active; exit node' in line
                        })
            
            return exit_nodes
        except Exception as e:
            logger.error(f"Failed to get exit nodes: {e}")
            return []
    
    @staticmethod
    def get_current_exit_node() -> str:
        """Get currently active exit node"""
        try:
            result = subprocess.run(
                ['tailscale', 'status'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            for line in result.stdout.split('\n'):
                if 'active; exit node' in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1]  # hostname
            return None
        except Exception as e:
            logger.error(f"Failed to get current exit node: {e}")
            return None
    
    @staticmethod
    def switch_exit_node(hostname: str) -> bool:
        """Switch to a different exit node"""
        try:
            logger.info(f"Switching to exit node: {hostname}")
            result = subprocess.run(
                ['sudo', 'tailscale', 'set', '--exit-node', hostname],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully switched to {hostname}")
                return True
            else:
                logger.error(f"Failed to switch: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Failed to switch exit node: {e}")
            return False
    
    @staticmethod
    def disable_exit_node() -> bool:
        """Disable exit node (use direct connection)"""
        try:
            result = subprocess.run(
                ['sudo', 'tailscale', 'set', '--exit-node='],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to disable exit node: {e}")
            return False


class AICaptchaSolver:
    """AI-based reCAPTCHA solver using YOLO model directly with Playwright"""
    
    MODEL_REPO = "DannyLuna/recaptcha-classification-57k"
    MODEL_FILE = "recaptcha_classification_57k.onnx"
    
    def __init__(self, page, status_callback=None):
        self.page = page
        self.status_callback = status_callback
        self.model = None
        self._model_loaded = False
        logger.info("[AI Solver] Initialized AICaptchaSolver")
        
    def update_status(self, message: str, progress: int = 0):
        """Update status via callback"""
        logger.info(f"[AI Solver] {message}")
        if self.status_callback:
            self.status_callback(f"[AI] {message}", progress)
    
    async def load_model(self):
        """Load YOLO model from HuggingFace"""
        global YOLO_MODEL
        
        # Check if model is already loaded (pre-loaded at startup or cached)
        if YOLO_MODEL is not None:
            self.update_status("Using pre-loaded AI model", 72)
            self.model = YOLO_MODEL
            self._model_loaded = True
            logger.info("[AI Solver] Using pre-loaded model")
            return True
        
        try:
            self.update_status("Downloading AI model from HuggingFace (this may take a moment)...", 70)
            logger.info("[AI Solver] Model not pre-loaded, downloading now...")
            
            # Download model from HuggingFace - this is blocking but necessary
            model_path = hf_hub_download(
                repo_id=self.MODEL_REPO,
                filename=self.MODEL_FILE
            )
            logger.info(f"[AI Solver] Model path: {model_path}")
            
            self.update_status("Loading YOLO model...", 72)
            self.model = YOLO(model_path, task='classify')
            YOLO_MODEL = self.model  # Cache globally
            self._model_loaded = True
            
            self.update_status("AI model loaded successfully!", 74)
            logger.info("[AI Solver] Model loaded and cached")
            return True
            
        except Exception as e:
            self.update_status(f"Failed to load model: {str(e)[:100]}", 70)
            logger.error(f"[AI Solver] Model loading error: {e}", exc_info=True)
            return False
    
    async def get_challenge_frame(self):
        """Find the reCAPTCHA challenge iframe"""
        frames = self.page.frames
        for frame in frames:
            if 'recaptcha' in frame.url and 'bframe' in frame.url:
                return frame
        return None
    
    async def get_challenge_text(self, frame) -> str:
        """Extract the challenge text (what to select)"""
        try:
            # Try multiple selectors for challenge text
            selectors = [
                '.rc-imageselect-desc-no-canonical strong',
                '.rc-imageselect-desc strong',
                '.rc-imageselect-instructions strong',
                'div.rc-imageselect-desc',
            ]
            
            for selector in selectors:
                element = await frame.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    if text:
                        return text.lower().strip()
            
            # Fallback: get all text from instructions
            instructions = await frame.query_selector('.rc-imageselect-instructions')
            if instructions:
                text = await instructions.inner_text()
                return text.lower()
                
        except Exception as e:
            logger.debug(f"Failed to get challenge text: {e}")
        
        return ""
    
    def get_target_classes(self, challenge_text: str) -> list:
        """Convert challenge text to target class IDs"""
        challenge_text = challenge_text.lower()
        
        for key, class_ids in CHALLENGE_MAPPING.items():
            if key in challenge_text:
                self.update_status(f"Looking for: {key}", 75)
                return class_ids
        
        # If no match found, log and return empty
        self.update_status(f"Unknown challenge: {challenge_text[:50]}", 75)
        return []
    
    async def get_tile_images(self, frame) -> list:
        """Download all tile images from the challenge"""
        tiles = []
        
        try:
            # Find all tile elements
            tile_elements = await frame.query_selector_all('.rc-image-tile-wrapper img, .rc-imageselect-tile img')
            
            if not tile_elements:
                # Try alternative selector
                tile_elements = await frame.query_selector_all('td.rc-imageselect-tile img')
            
            self.update_status(f"Found {len(tile_elements)} tiles", 76)
            
            for i, tile in enumerate(tile_elements):
                try:
                    src = await tile.get_attribute('src')
                    if src:
                        tiles.append({
                            'index': i,
                            'element': tile,
                            'src': src
                        })
                except Exception as e:
                    logger.debug(f"Failed to get tile {i}: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to get tile images: {e}")
        
        return tiles
    
    async def download_image(self, url: str) -> np.ndarray:
        """Download image and convert to numpy array"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.read()
                        # Convert to numpy array
                        nparr = np.frombuffer(data, np.uint8)
                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        return img
        except Exception as e:
            logger.error(f"Failed to download image: {e}")
        return None
    
    def classify_image(self, image: np.ndarray) -> tuple:
        """Classify image using YOLO model"""
        if self.model is None or image is None:
            return None, 0.0
        
        try:
            # Run inference
            results = self.model(image, verbose=False)
            
            if results and len(results) > 0:
                result = results[0]
                probs = result.probs
                
                if probs is not None:
                    top_class = probs.top1
                    confidence = probs.top1conf.item()
                    return top_class, confidence
                    
        except Exception as e:
            logger.error(f"Classification error: {e}")
        
        return None, 0.0
    
    async def solve_challenge(self, max_attempts: int = 5) -> bool:
        """Main method to solve the reCAPTCHA challenge"""
        
        if not AI_SOLVER_AVAILABLE:
            self.update_status("AI components not available", 70)
            logger.error("[AI Solver] AI_SOLVER_AVAILABLE is False - dependencies missing")
            return False
        
        # Load model if not loaded
        if not self._model_loaded:
            self.update_status("Loading AI model (first run may download ~500MB)...", 70)
            try:
                if not await self.load_model():
                    logger.error("[AI Solver] Model loading failed")
                    return False
            except Exception as e:
                logger.error(f"[AI Solver] Exception during model loading: {e}")
                self.update_status(f"Model loading error: {e}", 70)
                return False
        
        for attempt in range(max_attempts):
            self.update_status(f"AI solving attempt {attempt + 1}/{max_attempts}", 75)
            
            try:
                # Find challenge frame
                frame = await self.get_challenge_frame()
                if not frame:
                    self.update_status("Challenge frame not found - waiting...", 70)
                    logger.debug("[AI Solver] Challenge frame not found")
                    await asyncio.sleep(2)
                    continue
                
                # Get challenge text
                challenge_text = await self.get_challenge_text(frame)
                if not challenge_text:
                    self.update_status("Could not read challenge text - waiting...", 70)
                    logger.debug("[AI Solver] Could not get challenge text")
                    await asyncio.sleep(2)
                    continue
                
                self.update_status(f"Challenge: {challenge_text[:40]}...", 76)
                logger.info(f"[AI Solver] Challenge text: {challenge_text}")
                
                # Get target classes
                target_classes = self.get_target_classes(challenge_text)
                if not target_classes:
                    self.update_status(f"Unknown challenge type: '{challenge_text[:30]}' - cannot solve with AI", 70)
                    logger.warning(f"[AI Solver] Unknown challenge type: {challenge_text}")
                    # Don't return False immediately - maybe next attempt will work
                    await asyncio.sleep(2)
                    continue
                
                # Get tile images
                tiles = await self.get_tile_images(frame)
                if not tiles:
                    self.update_status("No tiles found - waiting...", 70)
                    logger.debug("[AI Solver] No tiles found")
                    await asyncio.sleep(2)
                    continue
                
                self.update_status(f"Analyzing {len(tiles)} tiles...", 76)
                
                # Classify each tile and click matching ones
                clicked_any = False
                tiles_analyzed = 0
                for tile in tiles:
                    try:
                        # Download and classify
                        img = await self.download_image(tile['src'])
                        if img is None:
                            logger.debug(f"[AI Solver] Failed to download tile {tile['index']}")
                            continue
                        
                        class_id, confidence = self.classify_image(img)
                        tiles_analyzed += 1
                        
                        class_name = YOLO_CLASSES.get(class_id, '?') if class_id is not None else 'unknown'
                        logger.debug(f"[AI Solver] Tile {tile['index']}: {class_name} ({confidence:.2f})")
                        
                        if class_id is not None and class_id in target_classes and confidence > 0.5:
                            self.update_status(f"Tile {tile['index']}: Match! ({class_name} {confidence:.2f})", 77)
                            
                            # Click the tile
                            await tile['element'].click()
                            clicked_any = True
                            await asyncio.sleep(0.3)  # Small delay between clicks
                            
                    except Exception as e:
                        logger.warning(f"[AI Solver] Error processing tile {tile['index']}: {e}")
                
                self.update_status(f"Analyzed {tiles_analyzed} tiles, clicked: {clicked_any}", 77)
                
                if not clicked_any:
                    self.update_status("No matching tiles found in this round", 77)
                
                # Wait for tiles to potentially refresh (dynamic challenge)
                await asyncio.sleep(1.5)
                
                # Click verify button
                try:
                    verify_btn = await frame.query_selector('#recaptcha-verify-button, .rc-button-default')
                    if verify_btn:
                        self.update_status("Clicking verify...", 78)
                        await verify_btn.click()
                        await asyncio.sleep(2.5)
                except Exception as e:
                    logger.debug(f"[AI Solver] Failed to click verify: {e}")
                
                # Check if challenge is still visible
                frame = await self.get_challenge_frame()
                if not frame:
                    self.update_status("Challenge solved!", 80)
                    return True
                
                # Check if there's an error message
                try:
                    error_msg = await frame.query_selector('.rc-imageselect-error-select-more, .rc-imageselect-error-dynamic-more')
                    if error_msg:
                        is_visible = await error_msg.is_visible()
                        if is_visible:
                            self.update_status("Need to select more tiles, retrying...", 76)
                            continue
                except Exception as e:
                    logger.debug(f"[AI Solver] Error checking error message: {e}")
                    
            except Exception as e:
                logger.error(f"[AI Solver] Exception in attempt {attempt + 1}: {e}")
                self.update_status(f"Error in attempt {attempt + 1}: {str(e)[:50]}", 70)
                await asyncio.sleep(2)
                continue
        
        self.update_status("AI solver exhausted all attempts - falling back to manual", 70)
        return False


class GeminiAPIKeyTracker:
    """
    Tracks API key usage, rate limits, and provides statistics
    Singleton pattern to persist across solver instances
    """
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if GeminiAPIKeyTracker._initialized:
            return
        GeminiAPIKeyTracker._initialized = True
        
        # Track usage per key: key_index -> {requests_this_minute, minute_start, total_requests, rate_limit_until}
        self.key_stats = {}
        # Free tier limit: 5 requests per minute for gemini-2.5-flash
        self.requests_per_minute_limit = 5
        # Cooldown after rate limit (seconds)
        self.rate_limit_cooldown = 60
        
    def _get_or_create_stats(self, key_index: int) -> dict:
        """Get or create stats for a key"""
        import time
        if key_index not in self.key_stats:
            self.key_stats[key_index] = {
                'requests_this_minute': 0,
                'minute_start': time.time(),
                'total_requests': 0,
                'successful_requests': 0,
                'rate_limit_until': 0,
                'last_rate_limit': None,
                'rate_limit_count': 0
            }
        return self.key_stats[key_index]
    
    def record_request(self, key_index: int, success: bool = True):
        """Record an API request for a key"""
        import time
        stats = self._get_or_create_stats(key_index)
        current_time = time.time()
        
        # Check if we've moved to a new minute
        if current_time - stats['minute_start'] >= 60:
            stats['requests_this_minute'] = 0
            stats['minute_start'] = current_time
        
        stats['requests_this_minute'] += 1
        stats['total_requests'] += 1
        if success:
            stats['successful_requests'] += 1
    
    def record_rate_limit(self, key_index: int, retry_after_seconds: float = None):
        """Record that a key hit rate limit"""
        import time
        stats = self._get_or_create_stats(key_index)
        current_time = time.time()
        
        # Use provided retry time or default cooldown
        cooldown = retry_after_seconds if retry_after_seconds else self.rate_limit_cooldown
        
        stats['rate_limit_until'] = current_time + cooldown
        stats['last_rate_limit'] = current_time
        stats['rate_limit_count'] += 1
        
        logger.info(f"[API Tracker] Key {key_index + 1} rate limited, will be available in {cooldown:.1f}s")
    
    def is_key_available(self, key_index: int) -> bool:
        """Check if a key is available (not rate limited)"""
        import time
        stats = self._get_or_create_stats(key_index)
        current_time = time.time()
        
        # Check if rate limit has expired
        if stats['rate_limit_until'] > current_time:
            return False
        
        # Check if we've used too many requests this minute (proactive limiting)
        if current_time - stats['minute_start'] < 60:
            if stats['requests_this_minute'] >= self.requests_per_minute_limit:
                return False
        
        return True
    
    def get_time_until_available(self, key_index: int) -> float:
        """Get seconds until key is available again"""
        import time
        stats = self._get_or_create_stats(key_index)
        current_time = time.time()
        
        # Check rate limit
        if stats['rate_limit_until'] > current_time:
            return stats['rate_limit_until'] - current_time
        
        # Check per-minute limit
        if current_time - stats['minute_start'] < 60:
            if stats['requests_this_minute'] >= self.requests_per_minute_limit:
                return 60 - (current_time - stats['minute_start'])
        
        return 0
    
    def get_remaining_requests(self, key_index: int) -> int:
        """Get remaining requests for this minute"""
        import time
        stats = self._get_or_create_stats(key_index)
        current_time = time.time()
        
        # Check if we've moved to a new minute
        if current_time - stats['minute_start'] >= 60:
            return self.requests_per_minute_limit
        
        remaining = self.requests_per_minute_limit - stats['requests_this_minute']
        return max(0, remaining)
    
    def get_key_status(self, key_index: int) -> dict:
        """Get detailed status for a key"""
        import time
        stats = self._get_or_create_stats(key_index)
        current_time = time.time()
        
        is_available = self.is_key_available(key_index)
        time_until_available = self.get_time_until_available(key_index)
        remaining = self.get_remaining_requests(key_index)
        
        return {
            'key_index': key_index,
            'is_available': is_available,
            'remaining_this_minute': remaining,
            'limit_per_minute': self.requests_per_minute_limit,
            'time_until_available': round(time_until_available, 1),
            'total_requests': stats['total_requests'],
            'successful_requests': stats['successful_requests'],
            'rate_limit_count': stats['rate_limit_count'],
            'last_rate_limit': stats['last_rate_limit']
        }
    
    def get_all_keys_status(self, num_keys: int) -> list:
        """Get status for all keys"""
        return [self.get_key_status(i) for i in range(num_keys)]
    
    def get_best_key(self, num_keys: int) -> int:
        """Get the best available key (most remaining requests)"""
        best_key = None
        best_remaining = -1
        
        for i in range(num_keys):
            if self.is_key_available(i):
                remaining = self.get_remaining_requests(i)
                if remaining > best_remaining:
                    best_remaining = remaining
                    best_key = i
        
        return best_key
    
    def get_summary(self, num_keys: int) -> dict:
        """Get a summary of all keys status"""
        import time
        statuses = self.get_all_keys_status(num_keys)
        
        available_keys = sum(1 for s in statuses if s['is_available'])
        total_remaining = sum(s['remaining_this_minute'] for s in statuses if s['is_available'])
        total_requests = sum(s['total_requests'] for s in statuses)
        total_rate_limits = sum(s['rate_limit_count'] for s in statuses)
        
        # Find next available key time if none available
        next_available_in = None
        if available_keys == 0:
            times = [s['time_until_available'] for s in statuses]
            if times:
                next_available_in = min(times)
        
        return {
            'total_keys': num_keys,
            'available_keys': available_keys,
            'total_remaining_requests': total_remaining,
            'total_requests_made': total_requests,
            'total_rate_limits_hit': total_rate_limits,
            'next_available_in': next_available_in,
            'keys_detail': statuses
        }


# Global tracker instance
_api_key_tracker = None

def get_api_key_tracker() -> GeminiAPIKeyTracker:
    """Get the global API key tracker instance"""
    global _api_key_tracker
    if _api_key_tracker is None:
        _api_key_tracker = GeminiAPIKeyTracker()
    return _api_key_tracker


class GeminiCaptchaSolver:
    """
    Gemini AI-based reCAPTCHA solver
    Uses Google's Gemini API to analyze CAPTCHA images and determine correct tiles
    
    Improvements based on GitHub research (njraladdin/recaptcha-v2-solver):
    - Better prompt engineering for grid analysis
    - Handling dynamic tile replacement (tiles that refresh after clicking)
    - Detecting "Next" vs "Verify" button scenarios
    - Proper waiting for new tiles to load
    """
    
    def __init__(self, page, api_keys: list, current_key_index: int = 0, 
                 model: str = 'gemini-2.5-flash', prompt: str = None, 
                 status_callback=None, dynamic_recheck: bool = True,
                 debug_save: bool = False):
        self.page = page
        self.api_keys = api_keys or []
        self.current_key_index = current_key_index
        self.model = model
        self.prompt = prompt or self._default_prompt()
        self.status_callback = status_callback
        self.dynamic_recheck = dynamic_recheck  # Re-analyze after each click in dynamic mode
        self.debug_save = debug_save  # Save images and responses to debug folder
        
        # Debug folder setup
        self.debug_folder = None
        if self.debug_save:
            self._setup_debug_folder()
        
        # Use global tracker
        self.tracker = get_api_key_tracker()
        
        # Track rate limits per key with timestamps (key_index -> timestamp when rate limited)
        self.rate_limited_keys = {}
        # How long to wait before retrying a rate-limited key (seconds)
        self.rate_limit_cooldown = 60
        
        # Track clicked tiles to avoid re-clicking same position in dynamic mode (only used when dynamic_recheck=False)
        self.clicked_positions = set()
        # Track if we're in dynamic tile mode (tiles refresh after click)
        self.is_dynamic_mode = False
        
        # Counter for debug files
        self.debug_counter = 0
        
        logger.info(f"[Gemini Solver] Initialized with {len(self.api_keys)} API keys, model: {model}, dynamic_recheck: {dynamic_recheck}, debug_save: {debug_save}")
    
    def _setup_debug_folder(self):
        """Create debug folder for saving images and responses"""
        import os
        from datetime import datetime
        
        # Create main debug folder
        base_folder = os.path.join(os.path.dirname(__file__), 'captcha_debug')
        os.makedirs(base_folder, exist_ok=True)
        
        # Create session folder with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.debug_folder = os.path.join(base_folder, f'session_{timestamp}')
        os.makedirs(self.debug_folder, exist_ok=True)
        
        logger.info(f"[Gemini] Debug folder created: {self.debug_folder}")
    
    def _save_debug_data(self, image_bytes: bytes, prompt: str, challenge_text: str, 
                         response_text: str = None, parsed_tiles: list = None):
        """Save debug data (image, prompt, response) to debug folder"""
        if not self.debug_save or not self.debug_folder:
            return
        
        import os
        from datetime import datetime
        
        self.debug_counter += 1
        timestamp = datetime.now().strftime('%H%M%S')
        prefix = f"{self.debug_counter:03d}_{timestamp}"
        
        try:
            # Save image
            image_path = os.path.join(self.debug_folder, f"{prefix}_captcha.jpg")
            with open(image_path, 'wb') as f:
                f.write(image_bytes)
            
            # Save prompt and response as text file
            info_path = os.path.join(self.debug_folder, f"{prefix}_info.txt")
            with open(info_path, 'w', encoding='utf-8') as f:
                f.write(f"=== CAPTCHA Debug Info ===\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Challenge: {challenge_text}\n")
                f.write(f"Model: {self.model}\n")
                f.write(f"API Key Index: {self.current_key_index + 1}/{len(self.api_keys)}\n")
                f.write(f"\n=== PROMPT ===\n")
                f.write(prompt)
                f.write(f"\n\n=== GEMINI RESPONSE ===\n")
                f.write(response_text if response_text else "(no response)")
                f.write(f"\n\n=== PARSED TILES ===\n")
                if parsed_tiles:
                    f.write(f"Tiles to click (1-based): {[t+1 for t in parsed_tiles]}\n")
                    f.write(f"Tiles to click (0-based): {parsed_tiles}\n")
                else:
                    f.write("No tiles parsed\n")
            
            logger.info(f"[Gemini] Debug saved: {prefix}_captcha.jpg, {prefix}_info.txt")
            
        except Exception as e:
            logger.warning(f"[Gemini] Failed to save debug data: {e}")
    
    async def click_tile_random(self, tile) -> bool:
        """
        Click on a tile at a random position within it (more human-like)
        
        Instead of clicking exactly at center, we add random offset.
        This helps avoid detection by making clicks look more natural.
        
        Args:
            tile: Playwright element handle for the tile
            
        Returns:
            True if click succeeded
        """
        import random
        
        try:
            # Get tile bounding box
            box = await tile.bounding_box()
            if not box:
                # Fallback to regular click if we can't get bounding box
                await tile.click()
                return True
            
            width = box['width']
            height = box['height']
            
            # Calculate random position within tile
            # Use padding of 15-20% from edges to avoid clicking too close to borders
            padding_x = width * 0.18
            padding_y = height * 0.18
            
            # Random position within the safe area
            rand_x = random.uniform(padding_x, width - padding_x)
            rand_y = random.uniform(padding_y, height - padding_y)
            
            # Click at random position (position is relative to element's top-left corner)
            await tile.click(position={'x': rand_x, 'y': rand_y})
            
            logger.debug(f"[Gemini] Clicked tile at random position ({rand_x:.1f}, {rand_y:.1f}) within ({width:.0f}x{height:.0f})")
            return True
            
        except Exception as e:
            logger.warning(f"[Gemini] Random click failed, using regular click: {e}")
            try:
                await tile.click()
                return True
            except:
                return False
    
    def _default_prompt(self) -> str:
        """
        Improved prompt based on research - clearer instructions for grid analysis
        """
        return '''You are analyzing a CAPTCHA image grid. Your task is to identify which tiles contain the requested object.

IMPORTANT RULES:
1. The grid is numbered 1-9 (for 3x3) or 1-16 (for 4x4), left-to-right, top-to-bottom
2. Return ONLY the tile numbers that clearly contain the object
3. Format: Just numbers separated by commas (e.g., "1, 4, 7")
4. If a tile only PARTIALLY shows the object, still include it
5. Be GENEROUS - include any tile where the object is visible, even partially
6. If truly no tiles match, respond with "none"

Grid numbering for 3x3:
[1][2][3]
[4][5][6]
[7][8][9]

Grid numbering for 4x4:
[1][2][3][4]
[5][6][7][8]
[9][10][11][12]
[13][14][15][16]'''
    
    def update_status(self, message: str, progress: int = 0):
        """Update status via callback"""
        logger.info(f"[Gemini] {message}")
        # Also log as STEP for easy filtering
        logger.info(f"[STEP] [Gemini] {message}")
        if self.status_callback:
            self.status_callback(f"[Gemini] {message}", progress)
    
    def log_step(self, message: str):
        """Log an important step for debugging"""
        logger.info(f"[STEP] [Gemini] {message}")
    
    def get_current_api_key(self) -> str:
        """Get current API key, skip rate-limited ones (unless cooldown expired)"""
        import time
        
        if not self.api_keys:
            return None
        
        # Use tracker to find best available key
        best_key = self.tracker.get_best_key(len(self.api_keys))
        
        if best_key is not None:
            self.current_key_index = best_key
            remaining = self.tracker.get_remaining_requests(best_key)
            self.update_status(f"Using API key {best_key + 1}/{len(self.api_keys)} ({remaining} requests remaining)", 71)
            return self.api_keys[best_key]
        
        # All keys are rate limited - check when next one is available
        summary = self.tracker.get_summary(len(self.api_keys))
        if summary['next_available_in']:
            wait_time = int(summary['next_available_in'])
            self.update_status(f"All keys rate limited! Next available in {wait_time}s...", 70)
        else:
            self.update_status("All API keys are rate limited!", 70)
        
        return None
    
    def rotate_key(self):
        """Rotate to the next available API key"""
        if len(self.api_keys) > 1:
            # Find next available key
            for i in range(1, len(self.api_keys)):
                next_index = (self.current_key_index + i) % len(self.api_keys)
                if self.tracker.is_key_available(next_index):
                    self.current_key_index = next_index
                    remaining = self.tracker.get_remaining_requests(next_index)
                    self.update_status(f"Rotated to API key {next_index + 1}/{len(self.api_keys)} ({remaining} remaining)", 71)
                    return
            
            # No available key, just rotate anyway
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            self.update_status(f"Rotated to API key {self.current_key_index + 1}/{len(self.api_keys)} (may be rate limited)", 71)
    
    def mark_key_rate_limited(self, key_index: int, retry_after: float = None):
        """Mark a key as rate limited with timestamp"""
        import time
        self.rate_limited_keys[key_index] = time.time()
        
        # Record in tracker
        self.tracker.record_rate_limit(key_index, retry_after)
        
        time_until = self.tracker.get_time_until_available(key_index)
        self.update_status(f"API key {key_index + 1} rate limited (available in {time_until:.0f}s)", 70)
    
    def get_keys_status(self) -> dict:
        """Get status of all API keys"""
        return self.tracker.get_summary(len(self.api_keys))
    
    async def get_challenge_frame(self):
        """Find the reCAPTCHA challenge iframe"""
        frames = self.page.frames
        for frame in frames:
            if 'recaptcha' in frame.url and 'bframe' in frame.url:
                return frame
        return None
    
    async def get_challenge_text(self, frame) -> str:
        """Extract the challenge text"""
        try:
            selectors = [
                '.rc-imageselect-desc-no-canonical strong',
                '.rc-imageselect-desc strong',
                '.rc-imageselect-instructions strong',
                'div.rc-imageselect-desc',
            ]
            
            for selector in selectors:
                element = await frame.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    if text:
                        return text.strip()
            
            # Fallback
            instructions = await frame.query_selector('.rc-imageselect-instructions')
            if instructions:
                text = await instructions.inner_text()
                return text.strip()
                
        except Exception as e:
            logger.debug(f"[Gemini] Failed to get challenge text: {e}")
        
        return ""
    
    async def capture_challenge_screenshot(self, frame) -> bytes:
        """Capture screenshot of the challenge area"""
        try:
            # Try to find the main challenge image area
            challenge_area = await frame.query_selector('.rc-imageselect-challenge')
            if challenge_area:
                screenshot = await challenge_area.screenshot()
                return screenshot
            
            # Fallback to full frame
            return await frame.locator('body').screenshot()
            
        except Exception as e:
            logger.error(f"[Gemini] Failed to capture screenshot: {e}")
            return None
    
    async def analyze_with_gemini(self, image_bytes: bytes, challenge_text: str, grid_size: int = 9) -> list:
        """
        Send image to Gemini API and get the tile numbers to click
        
        Args:
            image_bytes: Screenshot of the CAPTCHA challenge
            challenge_text: What to look for (e.g., "traffic lights")
            grid_size: 9 for 3x3 or 16 for 4x4 grid
        
        Returns:
            List of tile indices (0-based) to click, or empty list
        """
        import requests
        import base64
        from PIL import Image
        import io
        
        api_key = self.get_current_api_key()
        if not api_key:
            self.update_status("No available API keys!", 70)
            return []
        
        try:
            # Compress image to reduce size and API load
            original_size = len(image_bytes)
            try:
                img = Image.open(io.BytesIO(image_bytes))
                img_dimensions = f"{img.width}x{img.height}"
                
                # Resize if too large (max 800px width)
                if img.width > 800:
                    ratio = 800 / img.width
                    new_size = (800, int(img.height * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Convert to JPEG with compression
                output = io.BytesIO()
                img.convert('RGB').save(output, format='JPEG', quality=85)
                image_bytes = output.getvalue()
                logger.debug(f"[Gemini] Compressed image from {original_size} to {len(image_bytes)} bytes ({img_dimensions})")
            except Exception as e:
                logger.debug(f"[Gemini] Image compression failed, using original: {e}")
                img_dimensions = "unknown"
            
            # Encode image to base64
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
            
            # Determine grid type for prompt
            grid_type = "3x3 (tiles 1-9)" if grid_size == 9 else "4x4 (tiles 1-16)"
            
            # Build the prompt with specific grid info
            full_prompt = f"""{self.prompt}

CURRENT CHALLENGE:
- Grid type: {grid_type}
- Object to find: "{challenge_text}"
- Image dimensions: {img_dimensions}

Analyze the grid image and return ONLY the numbers of tiles containing: {challenge_text}

Remember: Be generous - if ANY part of the object is visible in a tile, include it."""
            
            # Make API request
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={api_key}"
            
            payload = {
                'contents': [{
                    'parts': [
                        {'text': full_prompt},
                        {
                            'inline_data': {
                                'mime_type': 'image/jpeg',
                                'data': image_b64
                            }
                        }
                    ]
                }],
                'generationConfig': {
                    'temperature': 0.1,
                    'maxOutputTokens': 100
                }
            }
            
            # Log key status before request
            remaining = self.tracker.get_remaining_requests(self.current_key_index)
            self.update_status(f"Sending to Gemini ({self.model})... [Key {self.current_key_index + 1}: {remaining} req left]", 73)
            
            # DETAILED DEBUG LOGGING
            logger.info(f"[Gemini] === API REQUEST ===")
            logger.info(f"[Gemini] Model: {self.model}")
            logger.info(f"[Gemini] Challenge: '{challenge_text}'")
            logger.info(f"[Gemini] Grid size: {grid_size} ({grid_type})")
            logger.info(f"[Gemini] Image size: {len(image_bytes)} bytes")
            logger.info(f"[Gemini] API Key: {self.current_key_index + 1}/{len(self.api_keys)} ({remaining} requests remaining)")
            
            response = requests.post(url, json=payload, timeout=30)
            
            # Record the request in tracker
            self.tracker.record_request(self.current_key_index, success=(response.status_code == 200))
            
            # DETAILED DEBUG LOGGING
            logger.info(f"[Gemini] === API RESPONSE ===")
            logger.info(f"[Gemini] Status code: {response.status_code}")
            
            if response.status_code == 429:
                # Rate limited - check error details and extract retry time
                retry_after = None
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', {}).get('message', 'Unknown')
                    logger.warning(f"[Gemini] Rate limit error: {error_msg}")
                    self.update_status(f"Rate limited: {error_msg[:60]}", 70)
                    
                    # Try to extract retry time from error message (e.g., "Please retry in 12.634587341s")
                    import re
                    retry_match = re.search(r'retry in ([\d.]+)s', error_msg)
                    if retry_match:
                        retry_after = float(retry_match.group(1))
                        logger.info(f"[Gemini] Parsed retry after: {retry_after}s")
                except:
                    pass
                
                self.mark_key_rate_limited(self.current_key_index, retry_after)
                
                # If we have more keys, try them after a small delay
                if len(self.api_keys) > 1:
                    self.rotate_key()
                    next_key_remaining = self.tracker.get_remaining_requests(self.current_key_index)
                    self.update_status(f"Rate limited, trying key {self.current_key_index + 1} ({next_key_remaining} remaining)...", 71)
                    await asyncio.sleep(2)  # Small delay before trying next key
                    return await self.analyze_with_gemini(image_bytes, challenge_text, grid_size)
                else:
                    # Only one key - wait based on retry_after or default
                    wait_time = min(retry_after or 15, 30)  # Max 30 seconds wait
                    self.update_status(f"Rate limited, waiting {wait_time:.0f}s before retry...", 70)
                    await asyncio.sleep(wait_time)
                    return []
            
            if response.status_code != 200:
                self.update_status(f"API error: {response.status_code}", 70)
                logger.error(f"[Gemini] API error response: {response.text[:500]}")
                return []
            
            # Parse response
            data = response.json()
            
            try:
                text_response = data['candidates'][0]['content']['parts'][0]['text'].strip()
                
                # DETAILED DEBUG LOGGING - show raw response
                logger.info(f"[Gemini] Raw response: '{text_response}'")
                self.update_status(f"Gemini says: {text_response}", 74)
                
                # Parse as lowercase for matching
                text_lower = text_response.lower()
                
                if text_lower in ['none', 'uncertain', '', 'no match', 'no tiles']:
                    logger.info(f"[Gemini] No tiles matched - response indicates no match")
                    # Save debug data even for "no match" responses
                    self._save_debug_data(image_bytes, full_prompt, challenge_text, text_response, [])
                    return []
                
                # Parse tile numbers
                # Handle various formats: "2, 5, 8" or "2,5,8" or "tiles 2, 5, 8" etc.
                import re
                numbers = re.findall(r'\d+', text_response)
                
                # Convert to 0-based indices (ensure within valid range)
                max_tile = grid_size  # 9 or 16
                tile_indices = [int(n) - 1 for n in numbers if 0 < int(n) <= max_tile]
                
                # DETAILED DEBUG LOGGING
                logger.info(f"[Gemini] Parsed numbers from response: {numbers}")
                logger.info(f"[Gemini] Valid tile indices (0-based): {tile_indices}")
                logger.info(f"[Gemini] Will click tiles (1-based): {[i+1 for i in tile_indices]}")
                
                # Save debug data (image, prompt, response)
                self._save_debug_data(image_bytes, full_prompt, challenge_text, text_response, tile_indices)
                
                self.update_status(f"Tiles to click: {[i+1 for i in tile_indices]}", 75)
                return tile_indices
                
            except (KeyError, IndexError) as e:
                logger.error(f"[Gemini] Failed to parse response structure: {e}")
                logger.error(f"[Gemini] Raw API response: {data}")
                # Save debug data for failed parsing
                self._save_debug_data(image_bytes, full_prompt, challenge_text, f"PARSE ERROR: {e}\nRaw: {data}", [])
                return []
                
        except requests.exceptions.Timeout:
            self.update_status("API request timed out", 70)
            logger.error("[Gemini] API request timed out after 30 seconds")
            return []
        except Exception as e:
            self.update_status(f"API error: {str(e)[:50]}", 70)
            logger.error(f"[Gemini] Unexpected error: {e}", exc_info=True)
            return []
    
    async def get_tile_elements(self, frame) -> list:
        """Get all clickable tile elements"""
        try:
            # Find all tiles
            tiles = await frame.query_selector_all('.rc-imageselect-tile')
            if not tiles:
                tiles = await frame.query_selector_all('td.rc-imageselect-tile')
            if not tiles:
                # Try another selector
                tiles = await frame.query_selector_all('.rc-image-tile-wrapper')
            
            return tiles
        except Exception as e:
            logger.error(f"[Gemini] Failed to get tiles: {e}")
            return []
    
    async def detect_captcha_type(self, frame) -> dict:
        """
        Detect the type of CAPTCHA challenge
        
        Returns:
            dict with:
            - grid_size: 9 (3x3) or 16 (4x4)
            - is_dynamic: True if tiles refresh after clicking (has "Verify" button)
            - has_next: True if there's a "Next" button (multi-round)
            - button_text: The text on the main action button
        """
        result = {
            'grid_size': 9,
            'is_dynamic': False,
            'has_next': False,
            'button_text': 'verify'
        }
        
        try:
            # Count tiles to determine grid size
            tiles = await frame.query_selector_all('.rc-imageselect-tile, td.rc-imageselect-tile')
            tile_count = len(tiles)
            
            if tile_count == 16:
                result['grid_size'] = 16
                logger.info(f"[Gemini] Detected 4x4 grid ({tile_count} tiles)")
            elif tile_count == 9:
                result['grid_size'] = 9
                logger.info(f"[Gemini] Detected 3x3 grid ({tile_count} tiles)")
            else:
                logger.info(f"[Gemini] Unusual tile count: {tile_count}, assuming 3x3")
            
            # Check for dynamic mode indicator (when tiles refresh after click)
            # Dynamic CAPTCHAs have the text "Click verify once there are none left"
            # or similar phrasing
            instructions = await frame.query_selector('.rc-imageselect-instructions')
            if instructions:
                text = await instructions.inner_text()
                text_lower = text.lower()
                
                # Dynamic mode indicators
                if 'once there are none left' in text_lower or 'click verify' in text_lower:
                    result['is_dynamic'] = True
                    logger.info(f"[Gemini] Detected DYNAMIC tile mode (tiles refresh after click)")
                
                # Multi-round indicator (has "Next" button)
                if 'if there are none' in text_lower:
                    result['has_next'] = True
                    logger.info(f"[Gemini] Detected MULTI-ROUND mode (Next button available)")
            
            # Also check button text
            verify_btn = await frame.query_selector('#recaptcha-verify-button')
            if verify_btn:
                btn_text = await verify_btn.inner_text()
                result['button_text'] = btn_text.lower().strip()
                logger.info(f"[Gemini] Button text: '{result['button_text']}'")
                
                if 'next' in result['button_text']:
                    result['has_next'] = True
                elif 'skip' in result['button_text']:
                    result['has_next'] = True  # Skip is similar to Next
                    
        except Exception as e:
            logger.debug(f"[Gemini] Error detecting CAPTCHA type: {e}")
        
        return result
    
    async def wait_for_tile_refresh(self, frame, timeout: float = 3.0) -> bool:
        """
        Wait for tiles to potentially refresh after clicking (for dynamic CAPTCHAs)
        
        Returns:
            True if tiles appeared to refresh
        """
        try:
            # Wait a moment for animation to start
            await asyncio.sleep(0.5)
            
            # Check if any tiles are fading/loading
            loading = await frame.query_selector('.rc-imageselect-tile.rc-imageselect-dynamic-selected, .rc-imageselect-progress')
            if loading:
                logger.debug("[Gemini] Tiles are refreshing, waiting...")
                # Wait for loading to complete
                await asyncio.sleep(timeout)
                return True
            
            # Default small wait even if no loading detected
            await asyncio.sleep(1.0)
            return False
            
        except Exception as e:
            logger.debug(f"[Gemini] Error waiting for tile refresh: {e}")
            await asyncio.sleep(1.0)
            return False
    
    async def solve_dynamic_with_recheck(self, frame, challenge_text: str, grid_size: int, max_clicks: int = 20) -> bool:
        """
        Solve dynamic CAPTCHA by clicking one tile at a time and re-analyzing after each click.
        
        This is the recommended approach for dynamic CAPTCHAs where tiles refresh after clicking.
        
        Args:
            frame: The reCAPTCHA challenge frame
            challenge_text: What to look for (e.g., "bus")
            grid_size: 9 for 3x3 or 16 for 4x4
            max_clicks: Maximum number of tile clicks before giving up
        
        Returns:
            True if solved successfully
        """
        total_clicked = 0
        consecutive_no_match = 0
        
        logger.info(f"[Gemini] Starting DYNAMIC RECHECK mode (max {max_clicks} clicks)")
        self.update_status("Dynamic recheck mode: analyzing one tile at a time...", 74)
        
        for click_num in range(max_clicks):
            # Check API key availability
            api_key = self.get_current_api_key()
            if not api_key:
                self.update_status("All keys rate limited, waiting...", 70)
                await asyncio.sleep(15)
                continue
            
            # Take fresh screenshot
            screenshot = await self.capture_challenge_screenshot(frame)
            if not screenshot:
                logger.warning("[Gemini] Failed to capture screenshot in recheck loop")
                await asyncio.sleep(1)
                continue
            
            # Get fresh tile elements
            tiles = await self.get_tile_elements(frame)
            if not tiles:
                logger.warning("[Gemini] No tiles found in recheck loop")
                await asyncio.sleep(1)
                continue
            
            # Analyze with Gemini
            self.update_status(f"Analyzing grid (click {click_num + 1})...", 74)
            tile_indices = await self.analyze_with_gemini(screenshot, challenge_text, grid_size)
            
            if not tile_indices:
                consecutive_no_match += 1
                logger.info(f"[Gemini] No matching tiles found (consecutive: {consecutive_no_match})")
                
                # If no match found 2 times in a row, probably done
                if consecutive_no_match >= 2:
                    self.update_status("No more matching tiles, clicking verify...", 78)
                    logger.info("[Gemini] No more tiles to click, attempting verify")
                    
                    try:
                        verify_btn = await frame.query_selector('#recaptcha-verify-button')
                        if verify_btn:
                            await verify_btn.click()
                            await asyncio.sleep(2.5)
                            
                            # Check if solved
                            frame_check = await self.get_challenge_frame()
                            if not frame_check:
                                self.update_status("Challenge solved!", 80)
                                logger.info(f"[Gemini] SUCCESS! Solved after {total_clicked} clicks")
                                return True
                            
                            # Check for errors
                            error_more = await frame_check.query_selector('.rc-imageselect-error-select-more, .rc-imageselect-error-dynamic-more')
                            if error_more and await error_more.is_visible():
                                logger.info("[Gemini] Need more tiles - resetting consecutive counter")
                                consecutive_no_match = 0
                                continue
                            
                            return False
                    except Exception as e:
                        logger.warning(f"[Gemini] Verify click failed: {e}")
                    
                    return False
                
                await asyncio.sleep(1)
                continue
            
            # Reset consecutive counter since we found a match
            consecutive_no_match = 0
            
            # Click ONLY THE FIRST matching tile
            first_tile_idx = tile_indices[0]
            
            if first_tile_idx < len(tiles):
                try:
                    logger.info(f"[Gemini] Clicking tile {first_tile_idx + 1} (found {len(tile_indices)} matches, clicking first)")
                    self.update_status(f"Clicking tile {first_tile_idx + 1}...", 75)
                    
                    # Click at random position within tile (more human-like)
                    await self.click_tile_random(tiles[first_tile_idx])
                    total_clicked += 1
                    
                    # Wait for tile to refresh
                    logger.debug("[Gemini] Waiting for tile refresh...")
                    await asyncio.sleep(0.5)
                    
                    # Wait for any loading animation
                    await self.wait_for_tile_refresh(frame, timeout=2.0)
                    
                except Exception as e:
                    logger.warning(f"[Gemini] Failed to click tile {first_tile_idx + 1}: {e}")
                    await asyncio.sleep(1)
        
        # Max clicks reached
        self.update_status(f"Max clicks ({max_clicks}) reached, trying verify...", 78)
        logger.warning(f"[Gemini] Max clicks reached ({total_clicked} clicks made)")
        
        try:
            verify_btn = await frame.query_selector('#recaptcha-verify-button')
            if verify_btn:
                await verify_btn.click()
                await asyncio.sleep(2.5)
                
                frame_check = await self.get_challenge_frame()
                if not frame_check:
                    self.update_status("Challenge solved!", 80)
                    return True
        except:
            pass
        
        return False
    
    async def solve_challenge(self, max_attempts: int = 8) -> bool:
        """
        Main method to solve reCAPTCHA using Gemini
        
        Two modes:
        1. dynamic_recheck=True (recommended): Click one tile, re-analyze, repeat
        2. dynamic_recheck=False (legacy): Click all tiles at once, then verify
        
        Returns:
            True if solved successfully
        """
        if not self.api_keys:
            self.update_status("No Gemini API keys configured!", 70)
            return False
        
        consecutive_rate_limits = 0
        # Reset clicked positions at start of solving session (for legacy mode)
        self.clicked_positions.clear()
        
        logger.info("=" * 60)
        logger.info("[Gemini] Starting CAPTCHA solving session")
        logger.info(f"[Gemini] Max attempts: {max_attempts}")
        logger.info(f"[Gemini] API keys available: {len(self.api_keys)}")
        logger.info(f"[Gemini] Dynamic recheck mode: {self.dynamic_recheck}")
        logger.info("=" * 60)
        
        for attempt in range(max_attempts):
            self.update_status(f"Gemini solving attempt {attempt + 1}/{max_attempts}", 72)
            logger.info(f"\n[Gemini] === ATTEMPT {attempt + 1}/{max_attempts} ===")
            
            try:
                # Check if we should wait for rate limit cooldown
                api_key = self.get_current_api_key()
                if not api_key:
                    consecutive_rate_limits += 1
                    if consecutive_rate_limits >= 2:
                        # Wait for cooldown
                        wait_time = min(30, self.rate_limit_cooldown // 2)
                        self.update_status(f"All keys rate limited, waiting {wait_time}s...", 70)
                        logger.warning(f"[Gemini] All keys rate limited, waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                        # Reset rate limits after waiting
                        self.rate_limited_keys.clear()
                        self.update_status("Rate limit cooldown complete, retrying...", 71)
                        consecutive_rate_limits = 0
                    continue
                else:
                    consecutive_rate_limits = 0
                
                # Find challenge frame
                frame = await self.get_challenge_frame()
                if not frame:
                    self.update_status("Challenge frame not found, waiting...", 70)
                    logger.debug("[Gemini] Challenge frame not found")
                    await asyncio.sleep(2)
                    continue
                
                # Get challenge text
                challenge_text = await self.get_challenge_text(frame)
                if not challenge_text:
                    self.update_status("Could not read challenge text", 70)
                    logger.debug("[Gemini] Could not read challenge text")
                    await asyncio.sleep(2)
                    continue
                
                self.update_status(f"Challenge: {challenge_text[:40]}...", 73)
                logger.info(f"[Gemini] Challenge text: '{challenge_text}'")
                
                # Detect CAPTCHA type
                captcha_info = await self.detect_captcha_type(frame)
                grid_size = captcha_info['grid_size']
                is_dynamic = captcha_info['is_dynamic']
                
                logger.info(f"[Gemini] CAPTCHA type: grid={grid_size}, dynamic={is_dynamic}, button='{captcha_info['button_text']}'")
                
                # === DYNAMIC RECHECK MODE ===
                # If dynamic mode and recheck is enabled, use the new approach
                if is_dynamic and self.dynamic_recheck:
                    logger.info("[Gemini] Using DYNAMIC RECHECK mode (click one, re-analyze, repeat)")
                    self.update_status("Dynamic mode: will re-analyze after each click", 73)
                    
                    solved = await self.solve_dynamic_with_recheck(frame, challenge_text, grid_size, max_clicks=15)
                    
                    if solved:
                        return True
                    
                    # Check if challenge frame still exists
                    frame = await self.get_challenge_frame()
                    if not frame:
                        self.update_status("Challenge solved!", 80)
                        return True
                    
                    # Continue to next attempt
                    continue
                
                # === LEGACY MODE (or non-dynamic CAPTCHA) ===
                # Capture screenshot
                screenshot = await self.capture_challenge_screenshot(frame)
                if not screenshot:
                    self.update_status("Failed to capture screenshot", 70)
                    logger.error("[Gemini] Failed to capture challenge screenshot")
                    await asyncio.sleep(2)
                    continue
                
                logger.info(f"[Gemini] Screenshot captured: {len(screenshot)} bytes")
                
                # Get tile elements
                tiles = await self.get_tile_elements(frame)
                if not tiles:
                    self.update_status("No tiles found", 70)
                    logger.error("[Gemini] No tile elements found")
                    await asyncio.sleep(2)
                    continue
                
                self.update_status(f"Found {len(tiles)} tiles, analyzing...", 74)
                logger.info(f"[Gemini] Found {len(tiles)} clickable tile elements")
                
                # Analyze with Gemini
                tile_indices = await self.analyze_with_gemini(screenshot, challenge_text, grid_size)
                
                if not tile_indices:
                    self.update_status("Gemini couldn't identify tiles, retrying...", 70)
                    logger.warning("[Gemini] No tiles identified by Gemini")
                    
                    # If dynamic mode and no tiles found, maybe we're done - try verify
                    if is_dynamic:
                        logger.info("[Gemini] Dynamic mode + no tiles = might be complete, trying verify")
                        try:
                            verify_btn = await frame.query_selector('#recaptcha-verify-button')
                            if verify_btn:
                                self.update_status("No more tiles found, clicking verify...", 78)
                                await verify_btn.click()
                                await asyncio.sleep(2.5)
                                
                                # Check if solved
                                frame = await self.get_challenge_frame()
                                if not frame:
                                    self.update_status("Challenge solved!", 80)
                                    logger.info("[Gemini] SUCCESS! Challenge solved after verify click")
                                    return True
                        except Exception as e:
                            logger.debug(f"[Gemini] Verify attempt failed: {e}")
                    
                    await asyncio.sleep(2)
                    continue
                
                # Click identified tiles with proper delays
                clicked = 0
                click_delay = 0.5 if is_dynamic else 0.3  # Longer delay for dynamic tiles
                
                logger.info(f"[Gemini] Clicking {len(tile_indices)} tiles with {click_delay}s delay...")
                
                for idx in tile_indices:
                    if idx < len(tiles):
                        try:
                            # Skip if already clicked this position in dynamic mode (legacy behavior)
                            if is_dynamic and not self.dynamic_recheck and idx in self.clicked_positions:
                                logger.debug(f"[Gemini] Skipping tile {idx+1} (already clicked)")
                                continue
                            
                            logger.debug(f"[Gemini] Clicking tile {idx+1}...")
                            # Click at random position within tile (more human-like)
                            await self.click_tile_random(tiles[idx])
                            clicked += 1
                            
                            if is_dynamic and not self.dynamic_recheck:
                                self.clicked_positions.add(idx)
                            
                            await asyncio.sleep(click_delay)
                            
                        except Exception as e:
                            logger.warning(f"[Gemini] Failed to click tile {idx+1}: {e}")
                
                self.update_status(f"Clicked {clicked} tiles", 76)
                logger.info(f"[Gemini] Successfully clicked {clicked} tiles")
                
                # Wait for potential tile refresh (especially important for dynamic mode)
                if is_dynamic:
                    self.update_status("Waiting for tiles to refresh...", 76)
                    await self.wait_for_tile_refresh(frame, timeout=2.5)
                else:
                    await asyncio.sleep(1.5)
                
                # Click verify button
                try:
                    verify_btn = await frame.query_selector('#recaptcha-verify-button, .rc-button-default')
                    if verify_btn:
                        btn_text = await verify_btn.inner_text()
                        self.update_status(f"Clicking {btn_text.strip()}...", 78)
                        logger.info(f"[Gemini] Clicking button: '{btn_text.strip()}'")
                        await verify_btn.click()
                        await asyncio.sleep(2.5)
                except Exception as e:
                    logger.warning(f"[Gemini] Failed to click verify button: {e}")
                
                # Check if solved
                frame = await self.get_challenge_frame()
                if not frame:
                    self.update_status("Challenge solved!", 80)
                    logger.info("[Gemini] SUCCESS! Challenge solved!")
                    return True
                
                # Check for error messages
                try:
                    # "Please select all matching images" or "Please try again"
                    error_select_more = await frame.query_selector('.rc-imageselect-error-select-more')
                    error_dynamic_more = await frame.query_selector('.rc-imageselect-error-dynamic-more')
                    error_incorrect = await frame.query_selector('.rc-imageselect-incorrect-response')
                    
                    if error_select_more and await error_select_more.is_visible():
                        self.update_status("Need more tiles, continuing...", 75)
                        logger.info("[Gemini] Error: Need to select more tiles")
                        continue
                    
                    if error_dynamic_more and await error_dynamic_more.is_visible():
                        self.update_status("Need more tiles (dynamic), continuing...", 75)
                        logger.info("[Gemini] Error: Need more tiles in dynamic mode")
                        # Clear clicked positions for fresh start
                        self.clicked_positions.clear()
                        continue
                    
                    if error_incorrect and await error_incorrect.is_visible():
                        self.update_status("Incorrect selection, retrying...", 75)
                        logger.info("[Gemini] Error: Incorrect selection")
                        # Clear clicked positions for fresh start
                        self.clicked_positions.clear()
                        continue
                        
                except Exception as e:
                    logger.debug(f"[Gemini] Error checking error messages: {e}")
                    
            except Exception as e:
                logger.error(f"[Gemini] Error in attempt {attempt + 1}: {e}", exc_info=True)
                self.update_status(f"Error: {str(e)[:50]}", 70)
                await asyncio.sleep(2)
        
        self.update_status("Gemini solver exhausted attempts", 70)
        logger.warning(f"[Gemini] Failed to solve after {max_attempts} attempts")
        return False


class CardChecker:
    """Class for checking card balance from rcbalance.com"""
    
    SITE_URL = "https://rcbalance.com"
    # reCAPTCHA site key for rcbalance.com (extracted from the page)
    RECAPTCHA_SITE_KEY = "6LfXFp0UAAAAAG_qc3vvlP7mf3vQ4xX8c8k6KmKv"
    
    def __init__(self, headless: bool = True, timeout: int = 60000, status_callback=None, max_retries: int = 5, cancel_check=None, captcha_mode: str = 'auto', gemini_settings: dict = None):
        """
        Args:
            headless: Run browser without display
            timeout: Maximum wait time (milliseconds)
            status_callback: Callback function for status updates
            max_retries: Maximum exit node switches for CAPTCHA
            cancel_check: Callback function that returns True if task should be cancelled
            captcha_mode: 'auto' = try exit nodes to bypass, 'manual' = wait for manual solve, 'ai' = use AI solver, 'gemini' = use Gemini AI
            gemini_settings: Dict with gemini_api_keys, gemini_current_key_index, gemini_model, gemini_prompt
        """
        self.headless = headless
        self.timeout = timeout
        self.browser = None
        self.page = None
        self.playwright = None
        self.status_callback = status_callback
        self.max_retries = max_retries
        self.cancel_check = cancel_check
        self._cancelled = False
        self.captcha_mode = captcha_mode  # 'auto', 'manual', 'ai', or 'gemini'
        self.gemini_settings = gemini_settings or {}
    
    def is_cancelled(self) -> bool:
        """Check if task has been cancelled"""
        if self._cancelled:
            return True
        if self.cancel_check and self.cancel_check():
            self._cancelled = True
            self.update_status("Task cancelled by user", 0)
            return True
        return False
    
    def force_cancel(self):
        """Force cancel the task immediately"""
        self._cancelled = True
        logger.info("Force cancel triggered!")
        
    async def force_close(self):
        """Force close browser immediately"""
        logger.info("Force closing browser...")
        try:
            if self.browser:
                await self.browser.close()
                self.browser = None
                logger.info("Browser force closed")
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")
        try:
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
                logger.info("Playwright stopped")
        except Exception as e:
            logger.warning(f"Error stopping playwright: {e}")
        
    def update_status(self, message: str, progress: int = 0):
        """Update status via callback"""
        logger.info(message)
        if self.status_callback:
            self.status_callback(message, progress)
        
    async def initialize(self):
        """Initialize browser"""
        self.update_status("Initializing browser...", 15)
        
        self.playwright = await async_playwright().start()
        
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ]
        )
        
        # Create context with realistic settings
        context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York'
        )
        
        # Script to hide automation
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)
        
        self.page = await context.new_page()
        self.page.set_default_timeout(self.timeout)
        
        self.update_status("Browser ready", 20)
        
    async def fill_card_form(self, card_number: str, exp_month: str, exp_year: str, cvv: str):
        """
        Fill card form
        
        Args:
            card_number: 16-digit card number
            exp_month: Expiration month (01-12)
            exp_year: Expiration year (2 digits)
            cvv: 3-digit CVV code
        """
        self.update_status("Filling card form...", 35)
        
        # Format card number with dashes
        formatted_card = f"{card_number[:4]}-{card_number[4:8]}-{card_number[8:12]}-{card_number[12:]}"
        
        # Fill card number
        card_input = await self.page.wait_for_selector('#CreditCardNumber', state='visible')
        await card_input.fill('')
        await card_input.type(formatted_card, delay=50)
        self.update_status(f"Entered card number: ****-****-****-{card_number[-4:]}", 45)
        
        await asyncio.sleep(0.3)
        
        # Fill expiration month
        month_input = await self.page.wait_for_selector('#ExpMonth', state='visible')
        await month_input.fill('')
        await month_input.type(exp_month.zfill(2), delay=50)
        self.update_status(f"Entered expiration month: {exp_month.zfill(2)}", 55)
        
        await asyncio.sleep(0.3)
        
        # Fill expiration year
        year_input = await self.page.wait_for_selector('#ExpYear', state='visible')
        await year_input.fill('')
        await year_input.type(exp_year, delay=50)
        self.update_status(f"Entered expiration year: {exp_year}", 60)
        
        await asyncio.sleep(0.3)
        
        # Fill CVV
        cvv_input = await self.page.wait_for_selector('#CVV', state='visible')
        await cvv_input.fill('')
        await cvv_input.type(cvv, delay=50)
        self.update_status("Entered CVV", 65)
        
    async def click_recaptcha(self) -> tuple:
        """
        Click on the reCAPTCHA checkbox
        
        Returns:
            (clicked: bool, challenge_appeared: bool)
        """
        self.update_status("Looking for reCAPTCHA checkbox...", 68)
        logger.debug("Starting reCAPTCHA click process...")
        
        try:
            # Wait for reCAPTCHA iframe to load
            logger.debug("Waiting 2s for reCAPTCHA iframe to load...")
            await asyncio.sleep(2)
            
            # Find the reCAPTCHA iframe
            recaptcha_frame = None
            frames = self.page.frames
            logger.debug(f"Found {len(frames)} frames on page")
            
            for frame in frames:
                logger.debug(f"Checking frame URL: {frame.url[:100]}...")
                if 'recaptcha' in frame.url and 'anchor' in frame.url:
                    recaptcha_frame = frame
                    self.update_status("Found reCAPTCHA iframe", 70)
                    logger.debug(f"Found reCAPTCHA anchor frame: {frame.url}")
                    break
            
            if recaptcha_frame:
                # Click the checkbox inside the iframe
                logger.debug("Waiting for #recaptcha-anchor checkbox...")
                checkbox = await recaptcha_frame.wait_for_selector('#recaptcha-anchor', timeout=10000)
                if checkbox:
                    self.update_status("Clicking 'I'm not a robot' checkbox...", 72)
                    logger.debug("Clicking reCAPTCHA checkbox...")
                    await checkbox.click()
                    logger.debug("Clicked! Waiting 3s for response...")
                    await asyncio.sleep(3)  # Wait for response
                    
                    # Check if a challenge appeared (image selection)
                    logger.debug("Checking if CAPTCHA challenge appeared...")
                    challenge_appeared = await self.check_captcha_challenge()
                    
                    if challenge_appeared:
                        self.update_status("CAPTCHA challenge appeared! (images)", 72)
                        logger.debug("CAPTCHA challenge detected - images required")
                        return (True, True)  # clicked, challenge appeared
                    else:
                        self.update_status("CAPTCHA passed without challenge!", 75)
                        logger.debug("CAPTCHA passed without image challenge!")
                        return (True, False)  # clicked, no challenge
            else:
                # Try alternative method - click on the recaptcha div
                self.update_status("Trying alternative reCAPTCHA click method...", 70)
                logger.debug("No reCAPTCHA iframe found, trying .g-recaptcha div...")
                recaptcha_div = await self.page.query_selector('.g-recaptcha')
                if recaptcha_div:
                    logger.debug("Found .g-recaptcha div, clicking...")
                    await recaptcha_div.click()
                    await asyncio.sleep(3)
                    challenge_appeared = await self.check_captcha_challenge()
                    logger.debug(f"Challenge appeared after div click: {challenge_appeared}")
                    return (True, challenge_appeared)
                    
        except Exception as e:
            self.update_status(f"reCAPTCHA click error: {e}", 70)
            
        return (False, False)
    
    async def check_captcha_challenge(self) -> bool:
        """
        Check if a CAPTCHA challenge (image selection) appeared
        
        Returns:
            True if challenge popup appeared
        """
        logger.debug("Checking for CAPTCHA challenge...")
        try:
            # Look for the challenge iframe (bframe)
            frames = self.page.frames
            logger.debug(f"Checking {len(frames)} frames for challenge iframe...")
            
            for frame in frames:
                if 'recaptcha' in frame.url and 'bframe' in frame.url:
                    # Challenge iframe found - check if it's visible
                    self.update_status("Detected CAPTCHA challenge iframe", 72)
                    logger.debug(f"Found bframe challenge iframe: {frame.url[:100]}")
                    return True
            
            # Also check for challenge popup in the page
            logger.debug("Checking for challenge popup iframe...")
            challenge_popup = await self.page.query_selector('iframe[title*="challenge"]')
            if challenge_popup:
                is_visible = await challenge_popup.is_visible()
                logger.debug(f"Challenge popup found, visible: {is_visible}")
                if is_visible:
                    return True
            
            # Check if recaptcha anchor shows checkmark (verified)
            logger.debug("Checking for reCAPTCHA checkmark (verified state)...")
            for frame in frames:
                if 'recaptcha' in frame.url and 'anchor' in frame.url:
                    try:
                        checkmark = await frame.query_selector('.recaptcha-checkbox-checkmark')
                        if checkmark:
                            style = await checkmark.get_attribute('style')
                            logger.debug(f"Checkmark found, style: {style}")
                            # If checkmark is visible, no challenge
                            if style and 'display' not in style:
                                logger.debug("Checkmark visible - CAPTCHA passed!")
                                return False
                    except Exception as check_err:
                        logger.debug(f"Error checking checkmark: {check_err}")
                        pass
            
            logger.debug("No challenge detected")
            return False
            
        except Exception as e:
            logger.debug(f"Challenge check error: {e}")
            return False
    
    async def solve_captcha_with_retry(self, card_number: str, exp_month: str, exp_year: str, cvv: str, max_retries: int = 5) -> bool:
        """
        Try to solve CAPTCHA, switch exit nodes if challenge appears
        
        Args:
            card_number, exp_month, exp_year, cvv: Card details for retry
            max_retries: Maximum number of exit node switches to try
            
        Returns:
            True if CAPTCHA was solved without challenge
        """
        # Check cancellation
        if self.is_cancelled():
            return False
        
        # Get available exit nodes
        exit_nodes = TailscaleManager.get_available_exit_nodes()
        current_node = TailscaleManager.get_current_exit_node()
        
        self.update_status(f"Found {len(exit_nodes)} available exit nodes", 68)
        
        # Filter out current node and offline nodes
        available_nodes = [n for n in exit_nodes if n['hostname'] != current_node and not n.get('active')]
        
        # Shuffle for randomness
        random.shuffle(available_nodes)
        
        tried_nodes = []
        
        for attempt in range(max_retries):
            # Check cancellation at each attempt
            if self.is_cancelled():
                return False
            
            self.update_status(f"CAPTCHA attempt {attempt + 1}/{max_retries}", 70)
            
            # Click reCAPTCHA and check for challenge
            clicked, challenge_appeared = await self.click_recaptcha()
            
            if self.is_cancelled():
                return False
            
            if not clicked:
                self.update_status("Failed to click reCAPTCHA", 70)
                continue
            
            if not challenge_appeared:
                # SUCCESS! No challenge, CAPTCHA passed
                self.update_status("CAPTCHA passed without challenge!", 80)
                return True
            
            # Challenge appeared - need to switch exit node
            self.update_status("Challenge appeared - switching exit node...", 72)
            
            if not available_nodes:
                self.update_status("No more exit nodes to try!", 72)
                # Wait for manual solve as last resort
                return await self.wait_for_captcha_solve()
            
            # Pick next exit node
            next_node = available_nodes.pop(0)
            tried_nodes.append(next_node['hostname'])
            
            self.update_status(f"Switching to: {next_node['hostname']}", 72)
            
            # Switch exit node
            if TailscaleManager.switch_exit_node(next_node['hostname']):
                self.update_status(f"Switched to {next_node['hostname']}", 73)
                
                # Check cancellation before network wait
                if self.is_cancelled():
                    return False
                
                # Wait for network to stabilize (increased wait time)
                logger.debug(f"Waiting for network to stabilize after switching to {next_node['hostname']}...")
                await asyncio.sleep(5)  # Increased from 3 to 5 seconds
                
                if self.is_cancelled():
                    return False
                
                # Close current browser and reinitialize
                logger.debug("Closing browser before reinitializing...")
                await self.close()
                await asyncio.sleep(2)
                
                if self.is_cancelled():
                    return False
                
                logger.debug("Reinitializing browser...")
                await self.initialize()
                
                # Navigate back to site with retry logic
                self.update_status("Reloading site with new IP...", 74)
                
                # Retry navigation up to 3 times
                nav_success = False
                for nav_attempt in range(3):
                    if self.is_cancelled():
                        return False
                    
                    try:
                        logger.debug(f"Navigation attempt {nav_attempt + 1}/3 to {self.SITE_URL}")
                        await self.page.goto(self.SITE_URL, wait_until='domcontentloaded', timeout=30000)
                        await self.page.wait_for_load_state('networkidle', timeout=15000)
                        nav_success = True
                        logger.debug("Navigation successful!")
                        break
                    except Exception as nav_error:
                        logger.debug(f"Navigation attempt {nav_attempt + 1} failed: {nav_error}")
                        self.update_status(f"Navigation failed (attempt {nav_attempt + 1}/3), retrying...", 74)
                        
                        if nav_attempt < 2:  # Don't wait after last attempt
                            await asyncio.sleep(3)  # Wait before retry
                
                if not nav_success:
                    self.update_status(f"Navigation failed after 3 attempts, trying next exit node...", 72)
                    continue  # Try next exit node
                
                if self.is_cancelled():
                    return False
                
                # Fill form again
                logger.debug("Filling card form again...")
                await self.fill_card_form(card_number, exp_month, exp_year, cvv)
                
            else:
                self.update_status(f"Failed to switch to {next_node['hostname']}", 72)
        
        # Check cancellation before final wait
        if self.is_cancelled():
            return False
        
        # All retries exhausted - wait for manual solve
        self.update_status("All exit nodes tried - waiting for manual CAPTCHA solve...", 75)
        return await self.wait_for_captcha_solve()
    
    async def wait_for_captcha_solve(self) -> bool:
        """
        Wait for CAPTCHA to be solved (manually or automatically)
        
        Returns:
            True if CAPTCHA was solved
        """
        self.update_status("Waiting for CAPTCHA verification...", 75)
        
        # Check submit button status
        max_wait = 120  # 2 minutes for CAPTCHA
        check_interval = 2  # Check every 2 seconds
        
        for i in range(max_wait // check_interval):
            # Check cancellation
            if self.is_cancelled():
                return False
            
            try:
                # Check if submit button is enabled
                submit_btn = await self.page.query_selector('#btnSubmit')
                if submit_btn:
                    is_disabled = await submit_btn.get_attribute('disabled')
                    if not is_disabled:
                        self.update_status("reCAPTCHA verified - submit button enabled!", 80)
                        return True
                        
                # Check if captcha is checked
                captcha_response = await self.page.evaluate("""
                    () => {
                        const response = document.querySelector('[name="g-recaptcha-response"]');
                        return response && response.value.length > 0;
                    }
                """)
                
                if captcha_response:
                    self.update_status("reCAPTCHA response received", 80)
                    return True
                    
            except Exception as e:
                logger.debug(f"CAPTCHA check: {e}")
                
            await asyncio.sleep(check_interval)
            if i % 5 == 0:
                self.update_status(f"Waiting for CAPTCHA verification... {i * check_interval}s elapsed", 75)
                
        self.update_status("CAPTCHA wait timeout", 70)
        return False
    
    async def solve_captcha_manually(self) -> bool:
        """
        Legacy method - just wait for CAPTCHA solve
        
        Returns:
            True if CAPTCHA was solved
        """
        return await self.wait_for_captcha_solve()
    
    async def solve_captcha_with_ai(self) -> bool:
        """
        Solve CAPTCHA using AI vision model directly with our browser
        
        Returns:
            True if CAPTCHA was solved successfully
        """
        if not AI_SOLVER_AVAILABLE:
            self.update_status("AI Solver not available - dependencies not installed", 70)
            logger.warning("AI_SOLVER_AVAILABLE is False - check if ultralytics, opencv-python, aiohttp, huggingface_hub are installed")
            self.update_status("Falling back to manual CAPTCHA solve (wait 2 minutes or solve manually)...", 70)
            return await self.wait_for_captcha_solve()
        
        self.update_status("Starting AI CAPTCHA solver...", 70)
        logger.info("[AI Mode] Starting AI CAPTCHA solver")
        
        try:
            # Create AI solver with our page
            ai_solver = AICaptchaSolver(
                page=self.page,
                status_callback=self.status_callback
            )
            
            # Try to solve the challenge with more attempts
            solved = await ai_solver.solve_challenge(max_attempts=8)
            
            if solved:
                self.update_status("AI successfully solved CAPTCHA!", 80)
                logger.info("[AI Mode] CAPTCHA solved by AI")
                # Wait a bit and check if submit is enabled
                await asyncio.sleep(2)
                return await self.wait_for_captcha_solve()
            else:
                self.update_status("AI could not fully solve CAPTCHA - please complete manually if needed", 70)
                logger.info("[AI Mode] AI could not solve, falling back to manual")
                self.update_status("Waiting for manual completion (up to 2 minutes)...", 70)
                return await self.wait_for_captcha_solve()
                
        except Exception as e:
            self.update_status(f"AI solver error: {str(e)[:100]}", 70)
            logger.error(f"AI CAPTCHA solver error: {e}", exc_info=True)
            
            # Fallback to manual solving - don't close browser!
            self.update_status("AI error - falling back to manual CAPTCHA solve...", 70)
            self.update_status("Please solve the CAPTCHA manually (waiting up to 2 minutes)...", 70)
            return await self.wait_for_captcha_solve()
    
    async def solve_captcha_with_gemini(self) -> bool:
        """
        Solve CAPTCHA using Google Gemini AI
        
        Returns:
            True if CAPTCHA was solved successfully
        """
        api_keys = self.gemini_settings.get('gemini_api_keys', [])
        
        if not api_keys:
            self.update_status("No Gemini API keys configured!", 70)
            logger.warning("[Gemini Mode] No API keys configured")
            self.update_status("Falling back to manual CAPTCHA solve...", 70)
            return await self.wait_for_captcha_solve()
        
        self.update_status(f"Starting Gemini CAPTCHA solver ({len(api_keys)} keys available)...", 70)
        logger.info(f"[Gemini Mode] Starting Gemini CAPTCHA solver with {len(api_keys)} keys")
        
        try:
            # Create Gemini solver
            gemini_solver = GeminiCaptchaSolver(
                page=self.page,
                api_keys=api_keys,
                current_key_index=self.gemini_settings.get('gemini_current_key_index', 0),
                model=self.gemini_settings.get('gemini_model', 'gemini-2.0-flash'),
                prompt=self.gemini_settings.get('gemini_prompt'),
                status_callback=self.status_callback,
                dynamic_recheck=self.gemini_settings.get('gemini_dynamic_recheck', True),
                debug_save=self.gemini_settings.get('gemini_debug_save', False)
            )
            
            # Try to solve - more attempts if we need to wait for rate limits
            max_gemini_attempts = 10 if len(api_keys) == 1 else 8
            solved = await gemini_solver.solve_challenge(max_attempts=max_gemini_attempts)
            
            if solved:
                self.update_status("Gemini successfully solved CAPTCHA!", 80)
                logger.info("[Gemini Mode] CAPTCHA solved by Gemini")
                
                # Wait for reCAPTCHA to register the success
                self.update_status("Waiting for CAPTCHA verification to complete...", 82)
                await asyncio.sleep(3)  # Increased from 2 to 3 seconds
                
                # Verify the response is actually set
                for check in range(5):
                    captcha_response = await self.page.evaluate("""
                        () => {
                            const response = document.querySelector('[name="g-recaptcha-response"]');
                            return response && response.value.length > 0;
                        }
                    """)
                    if captcha_response:
                        logger.info("[Gemini Mode] reCAPTCHA response confirmed!")
                        break
                    logger.debug(f"[Gemini Mode] Waiting for response token... attempt {check + 1}")
                    await asyncio.sleep(1)
                
                return await self.wait_for_captcha_solve()
            else:
                self.update_status("Gemini could not solve CAPTCHA - please complete manually", 70)
                logger.info("[Gemini Mode] Gemini could not solve, falling back to manual")
                self.update_status("Waiting for manual completion (up to 2 minutes)...", 70)
                return await self.wait_for_captcha_solve()
                
        except Exception as e:
            self.update_status(f"Gemini solver error: {str(e)[:100]}", 70)
            logger.error(f"Gemini CAPTCHA solver error: {e}", exc_info=True)
            
            self.update_status("Gemini error - falling back to manual CAPTCHA solve...", 70)
            return await self.wait_for_captcha_solve()
        
    async def submit_and_get_result(self) -> dict:
        """
        Submit form and get result
        Waits properly for page to load before extracting data
        
        Returns:
            Dictionary containing result
        """
        self.update_status("Preparing to submit...", 85)
        
        try:
            # First verify reCAPTCHA response is present
            captcha_ready = await self.page.evaluate("""
                () => {
                    const response = document.querySelector('[name="g-recaptcha-response"]');
                    return response && response.value.length > 0;
                }
            """)
            
            if not captcha_ready:
                logger.warning("[Submit] reCAPTCHA response not ready, waiting...")
                await asyncio.sleep(2)
            
            # Click submit button
            self.update_status("Clicking submit button...", 86)
            submit_btn = await self.page.wait_for_selector('#btnSubmit:not([disabled])', timeout=10000)
            
            # Small delay before clicking to ensure everything is ready
            await asyncio.sleep(0.5)
            await submit_btn.click()
            
            self.update_status("Form submitted, waiting for response...", 88)
            
            # Wait for navigation/page change - this is crucial!
            try:
                # Wait for URL to change or new content to load
                await self.page.wait_for_load_state('networkidle', timeout=20000)
                self.update_status("Page loaded, looking for balance...", 90)
            except Exception as e:
                logger.warning(f"[Submit] networkidle timeout, trying anyway: {e}")
                # Fallback: wait a bit and continue
                await asyncio.sleep(3)
            
            # Wait specifically for balance element to appear
            balance_found = False
            for attempt in range(5):  # Try up to 5 times
                try:
                    await self.page.wait_for_selector('.card-info h5 strong', timeout=3000)
                    self.update_status("Balance element found!", 92)
                    balance_found = True
                    break
                except:
                    if attempt < 4:
                        logger.debug(f"[Submit] Balance element not found, attempt {attempt + 1}/5")
                        await asyncio.sleep(1)
            
            if not balance_found:
                # Check if we're still on the form page (CAPTCHA might have failed)
                current_url = self.page.url
                logger.warning(f"[Submit] Balance element not found after 5 attempts. URL: {current_url}")
                
                # Try to get any error message
                try:
                    page_text = await self.page.inner_text('body')
                    if 'invalid' in page_text.lower() or 'error' in page_text.lower():
                        return {
                            'success': False,
                            'error': 'Form submission may have failed - check if CAPTCHA was properly solved'
                        }
                except:
                    pass
            
            # Extract balance data
            result = await self.extract_balance()
            
            self.update_status("Data extracted successfully!", 98)
            return result
            
        except Exception as e:
            self.update_status(f"Error getting result: {e}", 90)
            logger.error(f"[Submit] Error: {e}", exc_info=True)
            
            # Take screenshot for debugging
            try:
                screenshot_path = f'error_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
                await self.page.screenshot(path=screenshot_path)
                logger.info(f"[Submit] Error screenshot saved: {screenshot_path}")
            except:
                pass
                
            return {
                'success': False,
                'error': str(e)
            }
            
    async def extract_balance(self) -> dict:
        """
        Extract balance and card info from result page
        OPTIMIZED: Get essential data quickly, skip non-essential
        
        Returns:
            Dictionary containing balance and info
        """
        self.update_status("Extracting balance...", 95)
        
        try:
            # NO WAITING - page should already have the data
            
            result_data = {
                'success': True,
                'timestamp': datetime.now().isoformat()
            }
            
            # Try to extract balance from the card-info section (PRIORITY)
            try:
                # Look for balance in the card info section: <h5><span>Balance</span><strong>$546.40</strong></h5>
                balance_element = await self.page.query_selector('.card-info h5 strong')
                if balance_element:
                    balance = await balance_element.inner_text()
                    balance = balance.strip()
                    result_data['balance'] = balance
                    self.update_status(f"Balance found: {balance}", 98)
                    
                    # GOT BALANCE! Get cardholder name quickly and return
                    try:
                        name_row = await self.page.query_selector('table.font-med tr:first-child td:last-child')
                        if name_row:
                            name = await name_row.inner_text()
                            result_data['cardholder_name'] = name.strip()
                    except:
                        pass
                    
                    # Return immediately - don't wait for transactions etc
                    result_data['message'] = 'Balance retrieved successfully'
                    return result_data
                    
            except Exception as e:
                logger.debug(f"Balance extraction method 1 failed: {e}")
            
            # Fallback: Try regex on page text (only if balance not found)
            if 'balance' not in result_data:
                page_text = await self.page.inner_text('body')
                balance_match = re.search(r'Balance\s*\$?([\d,]+\.?\d*)', page_text, re.IGNORECASE)
                if balance_match:
                    balance = '$' + balance_match.group(1)
                    result_data['balance'] = balance
                    self.update_status(f"Balance found: {balance}", 98)
                    result_data['message'] = 'Balance retrieved successfully'
                    return result_data
            
            # Only try to get cardholder name if we still don't have balance
            try:
                name_row = await self.page.query_selector('table.font-med tr:first-child td:last-child')
                if name_row:
                    name = await name_row.inner_text()
                    result_data['cardholder_name'] = name.strip()
            except Exception as e:
                logger.debug(f"Name extraction failed: {e}")
            
            # Try to extract address
            try:
                address_row = await self.page.query_selector('table.font-med tr:nth-child(2) td:last-child')
                if address_row:
                    address = await address_row.inner_text()
                    result_data['address'] = address.strip()
            except Exception as e:
                logger.debug(f"Address extraction failed: {e}")
            
            # Try to extract card last 4 digits
            try:
                card_last4 = await self.page.query_selector('.card-info h4 span:last-child')
                if card_last4:
                    last4 = await card_last4.inner_text()
                    result_data['card_last4'] = last4.strip()
            except Exception as e:
                logger.debug(f"Card last4 extraction failed: {e}")
            
            # Try to extract transactions
            try:
                transactions = []
                tx_rows = await self.page.query_selector_all('table.table-striped tbody tr')
                for row in tx_rows:
                    try:
                        desc_el = await row.query_selector('td:first-child span.font-weight-bold')
                        date_el = await row.query_selector('td:first-child')
                        amount_el = await row.query_selector('td.text-right')
                        
                        if desc_el and amount_el:
                            desc = await desc_el.inner_text()
                            amount = await amount_el.inner_text()
                            date_text = await date_el.inner_text()
                            # Extract date from the text
                            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*[AP]M)', date_text)
                            date = date_match.group(1) if date_match else ''
                            
                            transactions.append({
                                'description': desc.strip(),
                                'date': date.strip(),
                                'amount': amount.strip()
                            })
                    except:
                        continue
                
                if transactions:
                    result_data['transactions'] = transactions
                    self.update_status(f"Found {len(transactions)} transactions", 99)
            except Exception as e:
                logger.debug(f"Transactions extraction failed: {e}")
            
            # Check if we got the balance
            if 'balance' in result_data:
                self.update_status(f"SUCCESS! Balance: {result_data['balance']}", 100)
                result_data['message'] = 'Balance retrieved successfully'
                return result_data
            
            # If no balance found, check for errors
            page_text = await self.page.inner_text('body')
            error_patterns = ['invalid', 'error', 'incorrect', 'not found', 'expired', 'unable']
            
            for pattern in error_patterns:
                if re.search(pattern, page_text, re.IGNORECASE):
                    self.update_status(f"Error on page: {pattern}", 95)
                    return {
                        'success': False,
                        'error': 'Invalid card information or card not found',
                        'message': page_text[:500]
                    }
            
            # If nothing found
            self.update_status("Balance not found on page", 95)
            screenshot_path = f'result_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
            await self.page.screenshot(path=screenshot_path)
            
            return {
                'success': False,
                'error': 'Balance not found - please check screenshot',
                'screenshot': screenshot_path,
                'page_url': self.page.url
            }
            
        except Exception as e:
            self.update_status(f"Extraction error: {e}", 95)
            return {
                'success': False,
                'error': str(e)
            }
        
    async def check_balance(self, card_number: str, exp_month: str, exp_year: str, cvv: str) -> dict:
        """
        Main function to check balance
        
        Args:
            card_number: 16-digit card number
            exp_month: Expiration month
            exp_year: Expiration year (2 digits)
            cvv: CVV code
            
        Returns:
            Dictionary containing result
        """
        try:
            # Check cancellation before starting
            if self.is_cancelled():
                return {'success': False, 'error': 'Task cancelled', 'cancelled': True}
            
            # Initialize browser
            await self.initialize()
            
            if self.is_cancelled():
                return {'success': False, 'error': 'Task cancelled', 'cancelled': True}
            
            # Open website
            self.update_status(f"Opening {self.SITE_URL}...", 25)
            await self.page.goto(self.SITE_URL, wait_until='domcontentloaded')
            await self.page.wait_for_load_state('networkidle')
            
            if self.is_cancelled():
                return {'success': False, 'error': 'Task cancelled', 'cancelled': True}
            
            self.update_status("Website loaded successfully", 30)
            
            # Fill form
            await self.fill_card_form(card_number, exp_month, exp_year, cvv)
            
            if self.is_cancelled():
                return {'success': False, 'error': 'Task cancelled', 'cancelled': True}
            
            # CAPTCHA handling based on mode
            if self.captcha_mode == 'manual':
                self.update_status("CAPTCHA mode: MANUAL - Click checkbox and solve if needed", 68)
                # Just click and wait for manual solve
                clicked, challenge_appeared = await self.click_recaptcha()
                if challenge_appeared:
                    self.update_status("CAPTCHA challenge appeared - please solve manually!", 70)
                captcha_solved = await self.wait_for_captcha_solve()
            elif self.captcha_mode == 'gemini':
                # Gemini mode - use Google Gemini AI
                self.update_status("CAPTCHA mode: GEMINI - Using Google Gemini AI...", 68)
                
                api_keys = self.gemini_settings.get('gemini_api_keys', [])
                if not api_keys:
                    self.update_status("No Gemini API keys! Falling back to auto mode...", 68)
                    captcha_solved = await self.solve_captcha_with_retry(
                        card_number, exp_month, exp_year, cvv,
                        max_retries=self.max_retries
                    )
                else:
                    # First click the reCAPTCHA checkbox
                    clicked, challenge_appeared = await self.click_recaptcha()
                    
                    if not challenge_appeared:
                        # No challenge - already solved!
                        captcha_solved = await self.wait_for_captcha_solve()
                    else:
                        # Challenge appeared - use Gemini to solve
                        captcha_solved = await self.solve_captcha_with_gemini()
            elif self.captcha_mode == 'ai':
                # AI mode - use vision-ai-recaptcha-solver
                self.update_status("CAPTCHA mode: AI - Using AI vision model...", 68)
                
                if not AI_SOLVER_AVAILABLE:
                    self.update_status("AI Solver not installed! Falling back to auto mode...", 68)
                    captcha_solved = await self.solve_captcha_with_retry(
                        card_number, exp_month, exp_year, cvv,
                        max_retries=self.max_retries
                    )
                else:
                    # First click the reCAPTCHA checkbox
                    clicked, challenge_appeared = await self.click_recaptcha()
                    
                    if not challenge_appeared:
                        # No challenge - already solved!
                        captcha_solved = await self.wait_for_captcha_solve()
                    else:
                        # Challenge appeared - use AI to solve
                        captcha_solved = await self.solve_captcha_with_ai()
            else:
                # Auto mode - try exit node rotation
                self.update_status("CAPTCHA mode: AUTO - Trying exit node rotation...", 68)
                captcha_solved = await self.solve_captcha_with_retry(
                    card_number, exp_month, exp_year, cvv, 
                    max_retries=self.max_retries
                )
            
            if self.is_cancelled():
                return {'success': False, 'error': 'Task cancelled', 'cancelled': True}
            
            if not captcha_solved:
                # Check if submit button is still disabled
                submit_btn = await self.page.query_selector('#btnSubmit')
                if submit_btn:
                    is_disabled = await submit_btn.get_attribute('disabled')
                    if is_disabled:
                        return {
                            'success': False,
                            'error': 'CAPTCHA not solved after trying multiple exit nodes',
                            'message': 'reCAPTCHA verification failed - try again later'
                        }
            
            if self.is_cancelled():
                return {'success': False, 'error': 'Task cancelled', 'cancelled': True}
            
            # Submit form and get result
            result = await self.submit_and_get_result()
            
            return result
            
        except Exception as e:
            if self._cancelled:
                return {'success': False, 'error': 'Task cancelled', 'cancelled': True}
            self.update_status(f"Error: {e}", 0)
            return {
                'success': False,
                'error': str(e)
            }
            
        finally:
            await self.close()
            
    async def close(self):
        """Close browser"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.update_status("Browser closed", 100)


# تست مستقیم
async def main():
    """تست کردن CardChecker"""
    checker = CardChecker(headless=False)  # با نمایش برای حل CAPTCHA
    
    # اطلاعات تست (باید عوض بشه)
    result = await checker.check_balance(
        card_number="1234567890123456",
        exp_month="12",
        exp_year="25",
        cvv="123"
    )
    
    print("\n" + "=" * 50)
    print("📋 نتیجه:")
    print("=" * 50)
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
