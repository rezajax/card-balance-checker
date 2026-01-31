"""
Phone Browser Automation Module
===============================
Automate browser actions on Android phone via ADB.
"""

import time
import re
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from urllib.parse import quote

from .adb_controller import ADBController
from .logger import PhoneLogger, get_logger


@dataclass
class BrowserInfo:
    """Browser application information."""
    name: str
    package: str
    activity: str
    url_scheme: str = 'https'


# Known browsers
BROWSERS = {
    'brave': BrowserInfo(
        name='Brave',
        package='com.brave.browser',
        activity='com.brave.browser.BraveActivity'
    ),
    'chrome': BrowserInfo(
        name='Chrome',
        package='com.android.chrome',
        activity='com.google.android.apps.chrome.Main'
    ),
    'firefox': BrowserInfo(
        name='Firefox',
        package='org.mozilla.firefox',
        activity='org.mozilla.firefox.App'
    ),
    'edge': BrowserInfo(
        name='Edge',
        package='com.microsoft.emmx',
        activity='com.microsoft.emmx.MainActivity'
    ),
    'opera': BrowserInfo(
        name='Opera',
        package='com.opera.browser',
        activity='com.opera.browser.StartActivity'
    ),
    'samsung': BrowserInfo(
        name='Samsung Internet',
        package='com.sec.android.app.sbrowser',
        activity='com.sec.android.app.sbrowser.SBrowserMainActivity'
    ),
}


class PhoneBrowserAutomation:
    """
    Browser automation for Android phones.
    
    Features:
    - Open URLs
    - Navigate (back, forward, refresh)
    - Input text in address bar
    - Scroll pages
    - Take screenshots
    - Get page info (via accessibility/UI dump)
    - Handle browser tabs
    """
    
    def __init__(self, adb: ADBController, browser: str = 'brave', logger: Optional[PhoneLogger] = None):
        """
        Initialize browser automation.
        
        Args:
            adb: ADB controller instance
            browser: Browser to use ('brave', 'chrome', 'firefox', etc.)
            logger: Logger instance
        """
        self.adb = adb
        self.logger = logger or get_logger()
        
        # Get browser info
        browser_key = browser.lower()
        if browser_key not in BROWSERS:
            self.logger.browser(f"Unknown browser: {browser}, defaulting to Brave", level='WARNING')
            browser_key = 'brave'
        
        self.browser_info = BROWSERS[browser_key]
        self.logger.browser(f"Using browser: {self.browser_info.name}")
        
        # Check if browser is installed
        if not self._is_browser_installed():
            self.logger.browser(f"{self.browser_info.name} is not installed!", level='ERROR')
    
    def _is_browser_installed(self) -> bool:
        """Check if the browser is installed."""
        packages = self.adb.get_installed_packages()
        return self.browser_info.package in packages
    
    def launch(self) -> bool:
        """Launch the browser."""
        self.logger.browser(f"Launching {self.browser_info.name}")
        return self.adb.launch_app(self.browser_info.package)
    
    def close(self) -> bool:
        """Close the browser."""
        self.logger.browser(f"Closing {self.browser_info.name}")
        return self.adb.stop_app(self.browser_info.package)
    
    def is_running(self) -> bool:
        """Check if browser is running."""
        return self.adb.is_app_running(self.browser_info.package)
    
    def open_url(self, url: str, new_tab: bool = False) -> bool:
        """
        Open a URL in the browser.
        
        Args:
            url: URL to open
            new_tab: Whether to open in a new tab
        
        Returns:
            True if successful
        """
        # Ensure URL has scheme
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        
        self.logger.browser(f"Opening URL: {url}")
        
        # Use ADB to open URL
        success = self.adb.open_url(url)
        
        if success:
            # Wait for page to start loading
            time.sleep(2)
            self.logger.browser(f"URL opened: {url}")
        
        return success
    
    def go_back(self) -> bool:
        """Go back in browser history."""
        self.logger.browser("Navigating back")
        return self.adb.press_back()
    
    def refresh(self) -> bool:
        """
        Refresh the current page.
        Uses swipe down gesture to refresh.
        """
        self.logger.browser("Refreshing page")
        width, height = self.adb.get_screen_size()
        # Swipe down from top to refresh
        return self.adb.swipe(width // 2, 300, width // 2, 800, 300)
    
    def scroll_down(self, amount: int = 500) -> bool:
        """Scroll page down."""
        self.logger.browser(f"Scrolling down {amount}px")
        width, height = self.adb.get_screen_size()
        center_x = width // 2
        return self.adb.swipe(center_x, height // 2, center_x, height // 2 - amount, 300)
    
    def scroll_up(self, amount: int = 500) -> bool:
        """Scroll page up."""
        self.logger.browser(f"Scrolling up {amount}px")
        width, height = self.adb.get_screen_size()
        center_x = width // 2
        return self.adb.swipe(center_x, height // 2, center_x, height // 2 + amount, 300)
    
    def scroll_to_top(self) -> bool:
        """Scroll to top of page."""
        self.logger.browser("Scrolling to top")
        # Multiple fast swipes down
        for _ in range(5):
            self.scroll_up(1000)
            time.sleep(0.1)
        return True
    
    def scroll_to_bottom(self) -> bool:
        """Scroll to bottom of page."""
        self.logger.browser("Scrolling to bottom")
        # Multiple fast swipes up
        for _ in range(10):
            self.scroll_down(1000)
            time.sleep(0.1)
        return True
    
    def tap_address_bar(self) -> bool:
        """Tap the address bar to focus it."""
        self.logger.browser("Tapping address bar")
        width, height = self.adb.get_screen_size()
        # Address bar is usually at the top
        return self.adb.tap(width // 2, 100)
    
    def type_in_address_bar(self, text: str) -> bool:
        """
        Type text in the address bar.
        
        Args:
            text: Text to type (URL or search query)
        """
        self.logger.browser(f"Typing in address bar: {text}")
        
        # First tap address bar
        self.tap_address_bar()
        time.sleep(0.5)
        
        # Clear existing text (select all + delete)
        self.adb.press_key(29)  # CTRL+A (select all) - may not work on all devices
        time.sleep(0.2)
        
        # Input new text
        success = self.adb.input_text(text)
        
        return success
    
    def search(self, query: str) -> bool:
        """
        Perform a search.
        
        Args:
            query: Search query
        """
        self.logger.browser(f"Searching: {query}")
        
        self.tap_address_bar()
        time.sleep(0.5)
        
        self.adb.input_text(query)
        time.sleep(0.3)
        
        return self.adb.press_enter()
    
    def navigate_to(self, url: str) -> bool:
        """
        Navigate to a URL by typing it.
        
        Args:
            url: URL to navigate to
        """
        self.type_in_address_bar(url)
        time.sleep(0.3)
        return self.adb.press_enter()
    
    def take_screenshot(self, name: Optional[str] = None) -> Optional[str]:
        """Take a screenshot of the browser."""
        self.logger.browser("Taking screenshot")
        return self.adb.screenshot(name)
    
    def get_ui_dump(self) -> str:
        """
        Get UI hierarchy dump.
        Useful for finding elements on the page.
        """
        self.logger.browser("Getting UI dump", level='DEBUG')
        return self.adb.shell('uiautomator dump /dev/tty')
    
    def find_element_by_text(self, text: str) -> Optional[Tuple[int, int]]:
        """
        Find an element by text and return its center coordinates.
        
        Args:
            text: Text to search for
        
        Returns:
            (x, y) coordinates or None if not found
        """
        ui_dump = self.get_ui_dump()
        
        # Parse UI dump to find element with text
        pattern = rf'text="{re.escape(text)}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
        match = re.search(pattern, ui_dump)
        
        if match:
            x1, y1, x2, y2 = map(int, match.groups())
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2
            self.logger.browser(f"Found '{text}' at ({center_x}, {center_y})")
            return (center_x, center_y)
        
        self.logger.browser(f"Element with text '{text}' not found", level='WARNING')
        return None
    
    def tap_element_by_text(self, text: str) -> bool:
        """
        Find and tap an element by its text.
        
        Args:
            text: Text of the element to tap
        """
        coords = self.find_element_by_text(text)
        if coords:
            return self.adb.tap(coords[0], coords[1])
        return False
    
    def wait_for_page_load(self, timeout: int = 30) -> bool:
        """
        Wait for page to finish loading.
        Uses a simple heuristic based on UI stability.
        
        Args:
            timeout: Maximum time to wait in seconds
        """
        self.logger.browser("Waiting for page load...")
        
        start_time = time.time()
        last_dump = ""
        stable_count = 0
        
        while time.time() - start_time < timeout:
            current_dump = self.get_ui_dump()
            
            if current_dump == last_dump:
                stable_count += 1
                if stable_count >= 3:  # UI stable for 3 checks
                    self.logger.browser("Page loaded (UI stable)")
                    return True
            else:
                stable_count = 0
            
            last_dump = current_dump
            time.sleep(1)
        
        self.logger.browser("Page load timeout", level='WARNING')
        return False
    
    def clear_cache(self) -> bool:
        """Clear browser cache."""
        self.logger.browser(f"Clearing {self.browser_info.name} cache")
        return self.adb.shell(
            f'pm clear {self.browser_info.package}'
        ) != ""
    
    def clear_cookies(self) -> bool:
        """
        Clear browser cookies.
        Note: This clears all app data including settings.
        """
        self.logger.browser(f"Clearing {self.browser_info.name} data")
        self.adb.shell(f'pm clear {self.browser_info.package}')
        return True
    
    def open_new_tab(self) -> bool:
        """Open a new tab."""
        self.logger.browser("Opening new tab")
        # Most browsers: tap on tabs button, then new tab
        # This is browser-specific, using a generic approach
        width, height = self.adb.get_screen_size()
        
        # Try tapping the tabs button (usually top right area)
        self.adb.tap(width - 100, 100)
        time.sleep(0.5)
        
        # Try to find and tap "New tab" or "+" button
        if not self.tap_element_by_text("New tab"):
            # Try tapping a "+" area
            self.adb.tap(width // 2, 200)
        
        return True
    
    def close_current_tab(self) -> bool:
        """Close the current tab."""
        self.logger.browser("Closing current tab")
        width, _ = self.adb.get_screen_size()
        
        # Open tabs view
        self.adb.tap(width - 100, 100)
        time.sleep(0.5)
        
        # Try to find and tap close button
        return self.tap_element_by_text("Close") or self.adb.tap(width - 50, 100)
    
    def get_page_source(self) -> Optional[str]:
        """
        Try to get page source using browser devtools or accessibility.
        Note: Limited functionality without root.
        """
        self.logger.browser("Getting page source (limited)")
        # This is limited on non-rooted devices
        # Could use Chrome DevTools Protocol over ADB for Chrome
        return None
    
    def enable_developer_mode(self) -> bool:
        """
        Enable developer mode in browser if available.
        Browser-specific implementation needed.
        """
        self.logger.browser("Attempting to enable developer mode")
        # This varies by browser
        return False


class BrowserAutomationHelper:
    """Helper functions for common browser automation tasks."""
    
    @staticmethod
    def wait_and_tap(browser: PhoneBrowserAutomation, text: str, 
                     timeout: int = 10, interval: float = 0.5) -> bool:
        """Wait for an element to appear and tap it."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if browser.tap_element_by_text(text):
                return True
            time.sleep(interval)
        return False
    
    @staticmethod
    def fill_form_field(browser: PhoneBrowserAutomation, label: str, value: str) -> bool:
        """Find a form field by label and fill it."""
        coords = browser.find_element_by_text(label)
        if coords:
            # Tap slightly below the label (where input usually is)
            browser.adb.tap(coords[0], coords[1] + 50)
            time.sleep(0.3)
            browser.adb.input_text(value)
            return True
        return False
    
    @staticmethod
    def screenshot_sequence(browser: PhoneBrowserAutomation, name_prefix: str, 
                           scroll_times: int = 3) -> List[str]:
        """Take a series of screenshots while scrolling."""
        screenshots = []
        
        # Screenshot at top
        path = browser.take_screenshot(f"{name_prefix}_1.png")
        if path:
            screenshots.append(path)
        
        # Scroll and screenshot
        for i in range(scroll_times):
            browser.scroll_down(800)
            time.sleep(1)
            path = browser.take_screenshot(f"{name_prefix}_{i+2}.png")
            if path:
                screenshots.append(path)
        
        return screenshots
