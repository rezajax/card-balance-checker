#!/usr/bin/env python3
"""
Phone Automation Main Module
============================
Main entry point for phone automation with live logging.
"""

import sys
import os
import time
import threading
import subprocess
from datetime import datetime
from typing import Optional, List, Callable
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from phone.adb_controller import ADBController
from phone.scrcpy_manager import ScrcpyManager, ScrcpyPresets
from phone.browser_automation import PhoneBrowserAutomation
from phone.logger import PhoneLogger, get_logger, set_logger


class PhoneAutomation:
    """
    Main phone automation class.
    Integrates ADB, scrcpy, and browser automation with live logging.
    """
    
    def __init__(self, device_serial: Optional[str] = None, screen_width: int = 1920):
        """
        Initialize phone automation.
        
        Args:
            device_serial: Device serial to use
            screen_width: Screen width for positioning scrcpy window
        """
        # Initialize logger
        self.logger = PhoneLogger()
        set_logger(self.logger)
        
        self.logger.info("=" * 60, log_type='SYSTEM')
        self.logger.info("Phone Automation System Starting...", log_type='SYSTEM')
        self.logger.info("=" * 60, log_type='SYSTEM')
        
        # Initialize components
        self.adb = ADBController(device_serial=device_serial, logger=self.logger)
        self.scrcpy = ScrcpyManager(device_serial=self.adb.device_serial, logger=self.logger)
        self.browser: Optional[PhoneBrowserAutomation] = None
        
        self.screen_width = screen_width
        self._logcat_process: Optional[subprocess.Popen] = None
        self._logcat_thread: Optional[threading.Thread] = None
        self._running = True
        
        # Log device info
        self._log_device_info()
    
    def _log_device_info(self):
        """Log connected device information."""
        try:
            info = self.adb.get_device_info()
            self.logger.phone(f"Connected: {info.get('brand', '')} {info.get('model', '')}")
            self.logger.phone(f"Android: {info.get('android_version', '')} (SDK {info.get('sdk_version', '')})")
            self.logger.phone(f"Serial: {self.adb.device_serial}")
        except Exception as e:
            self.logger.error(f"Could not get device info: {e}", log_type='PHONE')
    
    def start_scrcpy(self, preset: str = 'right_panel') -> bool:
        """
        Start scrcpy with specified preset.
        
        Args:
            preset: 'right_panel', 'high_quality', 'low_latency', 'battery_saver'
        """
        self.logger.scrcpy(f"Starting scrcpy with '{preset}' preset")
        
        # Select preset
        if preset == 'right_panel':
            config = ScrcpyPresets.right_panel(self.screen_width)
        elif preset == 'high_quality':
            config = ScrcpyPresets.high_quality()
        elif preset == 'low_latency':
            config = ScrcpyPresets.low_latency()
        elif preset == 'battery_saver':
            config = ScrcpyPresets.battery_saver()
        else:
            config = ScrcpyPresets.right_panel(self.screen_width)
        
        return self.scrcpy.start(config)
    
    def stop_scrcpy(self) -> bool:
        """Stop scrcpy."""
        return self.scrcpy.stop()
    
    def start_logcat(self, filter_tags: Optional[List[str]] = None):
        """
        Start logcat streaming with live logging.
        
        Args:
            filter_tags: List of tags to filter (e.g., ['chromium', 'Brave'])
        """
        self.logger.adb("Starting logcat streaming...")
        
        # Build filter spec
        if filter_tags:
            filter_spec = ' '.join([f'{tag}:V' for tag in filter_tags]) + ' *:S'
        else:
            # Default: show important stuff, suppress verbose
            filter_spec = '*:I'
        
        self._logcat_process = self.adb.start_logcat(filter_spec)
        
        # Start thread to read logcat
        self._logcat_thread = threading.Thread(target=self._read_logcat, daemon=True)
        self._logcat_thread.start()
    
    def _read_logcat(self):
        """Read logcat output and log it."""
        if not self._logcat_process:
            return
        
        while self._running and self._logcat_process.poll() is None:
            try:
                line = self._logcat_process.stdout.readline()
                if line:
                    # Parse logcat line
                    line = line.strip()
                    if line:
                        # Determine log level from line
                        level = 'DEBUG'
                        if ' E ' in line or '/E ' in line:
                            level = 'ERROR'
                        elif ' W ' in line or '/W ' in line:
                            level = 'WARNING'
                        elif ' I ' in line or '/I ' in line:
                            level = 'INFO'
                        
                        self.logger.log('LOGCAT', level, line[:200])
            except Exception:
                break
    
    def stop_logcat(self):
        """Stop logcat streaming."""
        if self._logcat_process:
            self._logcat_process.terminate()
            self._logcat_process = None
            self.logger.adb("Logcat streaming stopped")
    
    def init_browser(self, browser: str = 'brave') -> PhoneBrowserAutomation:
        """
        Initialize browser automation.
        
        Args:
            browser: Browser to use ('brave', 'chrome', 'firefox')
        """
        self.browser = PhoneBrowserAutomation(self.adb, browser=browser, logger=self.logger)
        return self.browser
    
    def open_url(self, url: str) -> bool:
        """
        Open a URL in the browser.
        
        Args:
            url: URL to open
        """
        if not self.browser:
            self.init_browser()
        
        return self.browser.open_url(url)
    
    def screenshot(self, name: Optional[str] = None) -> Optional[str]:
        """Take a screenshot."""
        return self.adb.screenshot(name)
    
    def cleanup(self):
        """Clean up resources."""
        self._running = False
        self.stop_logcat()
        self.stop_scrcpy()
        self.logger.info("Phone automation cleaned up", log_type='SYSTEM')
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()


def print_banner():
    """Print startup banner."""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║           📱 Phone Automation System v1.0.0                   ║
║                                                              ║
║  Features:                                                   ║
║  • ADB Control & Automation                                  ║
║  • scrcpy Screen Mirroring                                   ║
║  • Browser Automation                                        ║
║  • Live Logging                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_log_header():
    """Print log header."""
    header = """
┌──────────────────────────────────────────────────────────────┐
│                        LIVE LOGS                             │
├──────────────────────────────────────────────────────────────┤
│  TIME     │ TYPE     │ MESSAGE                               │
├──────────────────────────────────────────────────────────────┤
"""
    print(header)


def run_demo():
    """Run a demonstration of the phone automation."""
    print_banner()
    print_log_header()
    
    with PhoneAutomation() as phone:
        # Start scrcpy on right side
        print("\n[Starting scrcpy...]")
        phone.start_scrcpy('right_panel')
        time.sleep(2)
        
        # Initialize browser
        print("\n[Initializing Brave browser...]")
        browser = phone.init_browser('brave')
        
        # Start logcat for browser logs
        print("\n[Starting logcat...]")
        phone.start_logcat(['chromium', 'Brave', 'WebView'])
        
        # Open browserleaks.com
        print("\n[Opening browserleaks.com...]")
        browser.open_url('https://browserleaks.com')
        
        # Wait for page load
        print("\n[Waiting for page load...]")
        time.sleep(5)
        
        # Take screenshot
        print("\n[Taking screenshot...]")
        screenshot_path = phone.screenshot()
        if screenshot_path:
            print(f"Screenshot saved: {screenshot_path}")
        
        # Keep running for demo
        print("\n[System running. Press Ctrl+C to stop...]")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[Shutting down...]")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Phone Automation System')
    parser.add_argument('--demo', action='store_true', help='Run demonstration')
    parser.add_argument('--url', type=str, help='URL to open')
    parser.add_argument('--browser', type=str, default='brave', 
                       choices=['brave', 'chrome', 'firefox', 'edge', 'samsung'],
                       help='Browser to use')
    parser.add_argument('--no-scrcpy', action='store_true', help='Don\'t start scrcpy')
    parser.add_argument('--device', type=str, help='Device serial')
    parser.add_argument('--screen-width', type=int, default=1920, help='Screen width for positioning')
    
    args = parser.parse_args()
    
    if args.demo:
        run_demo()
        return
    
    print_banner()
    print_log_header()
    
    with PhoneAutomation(device_serial=args.device, screen_width=args.screen_width) as phone:
        # Start scrcpy
        if not args.no_scrcpy:
            phone.start_scrcpy('right_panel')
            time.sleep(2)
        
        # Initialize browser
        browser = phone.init_browser(args.browser)
        
        # Start logcat
        phone.start_logcat(['chromium', 'Brave', 'WebView', 'System'])
        
        # Open URL if specified
        if args.url:
            browser.open_url(args.url)
        
        # Keep running
        print("\n[System running. Press Ctrl+C to stop...]")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[Shutting down...]")


if __name__ == '__main__':
    main()
