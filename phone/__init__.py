"""
Phone Automation Module
=======================
A comprehensive module for Android phone automation using ADB and scrcpy.

Features:
- Screen mirroring with scrcpy
- ADB command execution
- Touch/swipe/tap automation
- Browser automation
- Comprehensive logging
"""

from .adb_controller import ADBController
from .scrcpy_manager import ScrcpyManager
from .logger import PhoneLogger
from .browser_automation import PhoneBrowserAutomation
from .screen_reader import ScreenReader, UIElement, ScreenInfo
from .card_checker import PhoneCardChecker, CardInfo, CheckResult, CheckStatus

__all__ = [
    'ADBController',
    'ScrcpyManager', 
    'PhoneLogger',
    'PhoneBrowserAutomation',
    'ScreenReader',
    'UIElement',
    'ScreenInfo',
    'PhoneCardChecker',
    'CardInfo',
    'CheckResult',
    'CheckStatus'
]

__version__ = '1.0.0'
