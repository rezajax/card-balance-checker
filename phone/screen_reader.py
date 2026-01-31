"""
Screen Reader Module
====================
Read and parse phone screen content via ADB for automation.
"""

import re
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
from pathlib import Path

from .adb_controller import ADBController
from .logger import PhoneLogger, get_logger


@dataclass
class UIElement:
    """Represents a UI element on the screen."""
    text: str = ""
    content_desc: str = ""
    resource_id: str = ""
    class_name: str = ""
    package: str = ""
    bounds: str = ""
    clickable: bool = False
    scrollable: bool = False
    focusable: bool = False
    enabled: bool = True
    selected: bool = False
    checked: bool = False
    
    # Parsed bounds
    x1: int = 0
    y1: int = 0
    x2: int = 0
    y2: int = 0
    
    @property
    def center(self) -> Tuple[int, int]:
        """Get center coordinates."""
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)
    
    @property
    def width(self) -> int:
        return self.x2 - self.x1
    
    @property
    def height(self) -> int:
        return self.y2 - self.y1
    
    @property
    def display_text(self) -> str:
        """Get displayable text (text or content_desc)."""
        return self.text or self.content_desc
    
    def __str__(self):
        return f"UIElement(text='{self.text}', bounds={self.bounds}, clickable={self.clickable})"


@dataclass 
class ScreenInfo:
    """Information about the current screen."""
    package: str = ""
    activity: str = ""
    elements: List[UIElement] = field(default_factory=list)
    raw_xml: str = ""
    
    @property
    def text_elements(self) -> List[UIElement]:
        """Get elements with text."""
        return [e for e in self.elements if e.text or e.content_desc]
    
    @property
    def clickable_elements(self) -> List[UIElement]:
        """Get clickable elements."""
        return [e for e in self.elements if e.clickable]
    
    @property
    def all_text(self) -> str:
        """Get all text on screen."""
        texts = []
        for e in self.elements:
            if e.text:
                texts.append(e.text)
            elif e.content_desc:
                texts.append(e.content_desc)
        return "\n".join(texts)


class ScreenReader:
    """
    Read and parse phone screen content.
    
    Features:
    - Get UI hierarchy
    - Find elements by text, id, class
    - Get current activity
    - Extract all text from screen
    - Find clickable elements
    """
    
    def __init__(self, adb: ADBController, logger: Optional[PhoneLogger] = None):
        self.adb = adb
        self.logger = logger or get_logger()
        self._last_screen: Optional[ScreenInfo] = None
    
    def _parse_bounds(self, bounds_str: str) -> Tuple[int, int, int, int]:
        """Parse bounds string like '[0,0][1080,2400]'."""
        match = re.findall(r'\[(\d+),(\d+)\]', bounds_str)
        if len(match) >= 2:
            x1, y1 = int(match[0][0]), int(match[0][1])
            x2, y2 = int(match[1][0]), int(match[1][1])
            return x1, y1, x2, y2
        return 0, 0, 0, 0
    
    def _parse_element(self, node: ET.Element) -> UIElement:
        """Parse XML node into UIElement."""
        bounds = node.get('bounds', '')
        x1, y1, x2, y2 = self._parse_bounds(bounds)
        
        return UIElement(
            text=node.get('text', ''),
            content_desc=node.get('content-desc', ''),
            resource_id=node.get('resource-id', ''),
            class_name=node.get('class', ''),
            package=node.get('package', ''),
            bounds=bounds,
            clickable=node.get('clickable', 'false') == 'true',
            scrollable=node.get('scrollable', 'false') == 'true',
            focusable=node.get('focusable', 'false') == 'true',
            enabled=node.get('enabled', 'true') == 'true',
            selected=node.get('selected', 'false') == 'true',
            checked=node.get('checked', 'false') == 'true',
            x1=x1, y1=y1, x2=x2, y2=y2
        )
    
    def get_screen_info(self, force_refresh: bool = True) -> ScreenInfo:
        """
        Get current screen information.
        
        Args:
            force_refresh: Force new UI dump even if cached
        
        Returns:
            ScreenInfo with all elements
        """
        self.logger.phone("Getting screen info...", level='DEBUG')
        
        # Dump UI hierarchy
        self.adb._run_adb(['shell', 'uiautomator', 'dump', '/sdcard/ui_dump.xml'])
        result = self.adb._run_adb(['shell', 'cat', '/sdcard/ui_dump.xml'])
        
        xml_content = result.stdout.strip()
        
        screen = ScreenInfo(raw_xml=xml_content)
        
        # Get current activity
        activity_result = self.adb.shell('dumpsys activity activities | grep mResumedActivity')
        if activity_result:
            match = re.search(r'(\S+)/(\S+)', activity_result)
            if match:
                screen.package = match.group(1)
                screen.activity = match.group(2)
        
        # Parse XML
        try:
            root = ET.fromstring(xml_content)
            
            for node in root.iter('node'):
                element = self._parse_element(node)
                screen.elements.append(element)
            
            self.logger.phone(f"Found {len(screen.elements)} elements, {len(screen.text_elements)} with text")
        except ET.ParseError as e:
            self.logger.phone(f"XML parse error: {e}", level='ERROR')
        
        self._last_screen = screen
        return screen
    
    def find_by_text(self, text: str, exact: bool = False) -> List[UIElement]:
        """
        Find elements by text.
        
        Args:
            text: Text to search for
            exact: If True, require exact match
        
        Returns:
            List of matching elements (sorted by valid bounds first)
        """
        screen = self.get_screen_info()
        results = []
        
        for elem in screen.elements:
            elem_text = elem.text or elem.content_desc
            if exact:
                if elem_text == text:
                    results.append(elem)
            else:
                if text.lower() in elem_text.lower():
                    results.append(elem)
        
        # Sort by valid bounds (elements with real bounds first)
        results.sort(key=lambda e: (e.x2 == 0, -e.width * e.height))
        
        self.logger.phone(f"Found {len(results)} elements with text '{text}'")
        return results
    
    def find_by_id(self, resource_id: str) -> List[UIElement]:
        """Find elements by resource ID."""
        screen = self.get_screen_info()
        results = [e for e in screen.elements if resource_id in e.resource_id]
        self.logger.phone(f"Found {len(results)} elements with id '{resource_id}'")
        return results
    
    def find_by_class(self, class_name: str) -> List[UIElement]:
        """Find elements by class name."""
        screen = self.get_screen_info()
        results = [e for e in screen.elements if class_name in e.class_name]
        return results
    
    def find_clickable(self) -> List[UIElement]:
        """Find all clickable elements."""
        screen = self.get_screen_info()
        return screen.clickable_elements
    
    def find_editable(self) -> List[UIElement]:
        """Find editable text fields."""
        screen = self.get_screen_info()
        return [e for e in screen.elements if 'EditText' in e.class_name]
    
    def get_all_text(self) -> str:
        """Get all text visible on screen."""
        screen = self.get_screen_info()
        return screen.all_text
    
    def get_current_app(self) -> Tuple[str, str]:
        """Get current app package and activity."""
        screen = self.get_screen_info()
        return screen.package, screen.activity
    
    def tap_element(self, element: UIElement) -> bool:
        """Tap on an element."""
        x, y = element.center
        self.logger.phone(f"Tapping element at ({x}, {y}): {element.display_text[:30]}")
        return self.adb.tap(x, y)
    
    def tap_text(self, text: str) -> bool:
        """Find and tap element with text."""
        elements = self.find_by_text(text)
        if elements:
            # Prefer clickable elements
            clickable = [e for e in elements if e.clickable]
            target = clickable[0] if clickable else elements[0]
            return self.tap_element(target)
        
        self.logger.phone(f"No element found with text: {text}", level='WARNING')
        return False
    
    def wait_for_text(self, text: str, timeout: int = 10, interval: float = 1.0) -> Optional[UIElement]:
        """
        Wait for text to appear on screen.
        
        Args:
            text: Text to wait for
            timeout: Maximum wait time in seconds
            interval: Check interval in seconds
        
        Returns:
            Element if found, None if timeout
        """
        import time
        start = time.time()
        
        while time.time() - start < timeout:
            elements = self.find_by_text(text)
            if elements:
                return elements[0]
            time.sleep(interval)
        
        self.logger.phone(f"Timeout waiting for text: {text}", level='WARNING')
        return None
    
    def wait_for_activity(self, activity: str, timeout: int = 10) -> bool:
        """Wait for specific activity to be active."""
        import time
        start = time.time()
        
        while time.time() - start < timeout:
            pkg, act = self.get_current_app()
            if activity in act:
                return True
            time.sleep(1)
        
        return False
    
    def get_screen_summary(self) -> Dict[str, Any]:
        """Get a summary of current screen for debugging."""
        screen = self.get_screen_info()
        
        return {
            'package': screen.package,
            'activity': screen.activity,
            'total_elements': len(screen.elements),
            'text_elements': len(screen.text_elements),
            'clickable_elements': len(screen.clickable_elements),
            'texts': [e.display_text for e in screen.text_elements if e.display_text][:20],
            'clickable_texts': [e.display_text for e in screen.clickable_elements if e.display_text][:10]
        }
    
    def print_screen(self):
        """Print screen content for debugging."""
        summary = self.get_screen_summary()
        
        print(f"\n{'='*60}")
        print(f"📱 Screen: {summary['package']}")
        print(f"   Activity: {summary['activity']}")
        print(f"   Elements: {summary['total_elements']} total, {summary['text_elements']} with text")
        print(f"\n📝 Text on screen:")
        for text in summary['texts']:
            print(f"   • {text[:60]}")
        print(f"\n👆 Clickable elements:")
        for text in summary['clickable_texts']:
            print(f"   • {text[:60]}")
        print('='*60)
    
    def extract_key_value_pairs(self) -> Dict[str, str]:
        """
        Extract key-value pairs from screen (useful for info pages like browserleaks).
        Looks for label:value patterns based on layout position.
        """
        screen = self.get_screen_info()
        pairs = {}
        
        # Group elements by y position (same row)
        rows = {}
        for elem in screen.elements:
            if elem.text and elem.y1 > 0:
                row_key = elem.y1 // 50  # Group by ~50px rows
                if row_key not in rows:
                    rows[row_key] = []
                rows[row_key].append(elem)
        
        # Extract key-value from rows with 2 elements
        for row_key, elements in rows.items():
            elements.sort(key=lambda e: e.x1)  # Sort by x position
            
            if len(elements) >= 2:
                # First element is likely the label, second is value
                label = elements[0].text.strip().rstrip(':')
                value = elements[-1].text.strip()
                
                if label and value and label != value:
                    pairs[label] = value
        
        return pairs
    
    def get_page_data(self) -> Dict[str, Any]:
        """
        Get structured data from current page.
        Returns all text, key-value pairs, and clickable items.
        """
        screen = self.get_screen_info()
        
        return {
            'package': screen.package,
            'activity': screen.activity,
            'all_text': screen.all_text,
            'key_values': self.extract_key_value_pairs(),
            'clickable': [
                {'text': e.display_text, 'center': e.center}
                for e in screen.clickable_elements 
                if e.display_text and e.x2 > 0
            ],
            'element_count': len(screen.elements)
        }
    
    def find_and_tap(self, text: str) -> bool:
        """
        Find element by text and tap it.
        Returns True if found and tapped.
        """
        elements = self.find_by_text(text)
        
        # Find first element with valid bounds
        for elem in elements:
            if elem.x2 > 0:  # Has valid bounds
                x, y = elem.center
                self.logger.phone(f"Tapping '{text}' at ({x}, {y})")
                return self.adb.tap(x, y)
        
        self.logger.phone(f"No valid element found for '{text}'", level='WARNING')
        return False


# Convenience function
def read_screen(adb: ADBController) -> ScreenReader:
    """Create a screen reader instance."""
    return ScreenReader(adb)
