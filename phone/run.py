#!/usr/bin/env python3
"""
Quick Runner - Start phone automation with browserleaks.com
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from phone.adb_controller import ADBController
from phone.scrcpy_manager import ScrcpyManager, ScrcpyPresets
from phone.browser_automation import PhoneBrowserAutomation
from phone.logger import PhoneLogger, set_logger


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║           📱 Phone Automation - Quick Start                   ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    # Initialize
    logger = PhoneLogger()
    set_logger(logger)
    
    print("[1/5] Initializing ADB...")
    adb = ADBController(logger=logger)
    print(f"      Device: {adb.device_serial}")
    
    print("\n[2/5] Getting device info...")
    info = adb.get_device_info()
    print(f"      {info.get('brand', '')} {info.get('model', '')} (Android {info.get('android_version', '')})")
    
    print("\n[3/5] Starting scrcpy on right side of screen...")
    scrcpy = ScrcpyManager(device_serial=adb.device_serial, logger=logger)
    config = ScrcpyPresets.right_panel(1920)
    scrcpy.start(config)
    time.sleep(2)
    
    print("\n[4/5] Initializing Brave browser...")
    browser = PhoneBrowserAutomation(adb, browser='brave', logger=logger)
    
    print("\n[5/5] Opening browserleaks.com...")
    browser.open_url('https://browserleaks.com')
    
    print("\n" + "=" * 60)
    print("✅ READY! Phone mirroring active on right side of screen.")
    print("=" * 60)
    
    print("""
Commands available:
  - The phone screen is mirrored via scrcpy
  - You can control it with mouse/keyboard
  - browserleaks.com is now loading

Press Ctrl+C to stop.
""")
    
    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        scrcpy.stop()
        print("Done!")


if __name__ == '__main__':
    main()
