"""
ADB Controller Module
=====================
Comprehensive ADB automation for Android devices.
"""

import subprocess
import re
import time
import os
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass
from pathlib import Path

from .logger import PhoneLogger, get_logger


@dataclass
class DeviceInfo:
    """Information about a connected Android device."""
    serial: str
    state: str
    product: str
    model: str
    device: str
    transport_id: str
    usb_port: Optional[str] = None


@dataclass
class TouchEvent:
    """Touch event data."""
    x: int
    y: int
    action: str  # 'tap', 'swipe', 'long_press'
    duration: Optional[int] = None


class ADBController:
    """
    ADB Controller for Android device automation.
    
    Features:
    - Device management (connect, disconnect, list)
    - Touch/swipe/tap automation
    - App management (install, uninstall, launch)
    - Screen capture
    - Input text
    - Key events
    - Shell commands
    - Logcat streaming
    """
    
    def __init__(self, device_serial: Optional[str] = None, logger: Optional[PhoneLogger] = None):
        """
        Initialize ADB Controller.
        
        Args:
            device_serial: Specific device serial to use. If None, uses first available.
            logger: Logger instance. If None, uses global logger.
        """
        self.logger = logger or get_logger()
        self.device_serial = device_serial
        self.adb_path = self._find_adb()
        
        if not self.adb_path:
            self.logger.adb("ADB not found in PATH!", level='ERROR')
            raise RuntimeError("ADB not found. Please install Android SDK Platform Tools.")
        
        self.logger.adb(f"ADB found at: {self.adb_path}")
        
        # Auto-select device if not specified
        if not self.device_serial:
            devices = self.list_devices()
            if devices:
                self.device_serial = devices[0].serial
                self.logger.adb(f"Auto-selected device: {self.device_serial}")
            else:
                self.logger.adb("No devices connected", level='WARNING')
    
    def _find_adb(self) -> Optional[str]:
        """Find ADB executable."""
        try:
            result = subprocess.run(['which', 'adb'], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        
        # Check common paths
        common_paths = [
            '/usr/bin/adb',
            '/usr/local/bin/adb',
            os.path.expanduser('~/Android/Sdk/platform-tools/adb'),
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def _run_adb(self, args: List[str], timeout: int = 30, capture_output: bool = True) -> subprocess.CompletedProcess:
        """
        Run an ADB command.
        
        Args:
            args: ADB command arguments
            timeout: Command timeout in seconds
            capture_output: Whether to capture output
        
        Returns:
            CompletedProcess result
        """
        cmd = [self.adb_path]
        if self.device_serial:
            cmd.extend(['-s', self.device_serial])
        cmd.extend(args)
        
        cmd_str = ' '.join(cmd)
        self.logger.adb(f"Running: {cmd_str}", level='DEBUG')
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                timeout=timeout
            )
            
            if result.returncode != 0 and result.stderr:
                self.logger.adb(f"Error: {result.stderr.strip()}", level='ERROR')
            elif result.stdout:
                self.logger.adb(f"Output: {result.stdout.strip()[:200]}", level='DEBUG')
            
            return result
        except subprocess.TimeoutExpired:
            self.logger.adb(f"Command timed out: {cmd_str}", level='ERROR')
            raise
        except Exception as e:
            self.logger.adb(f"Command failed: {e}", level='ERROR')
            raise
    
    def list_devices(self) -> List[DeviceInfo]:
        """List all connected devices."""
        result = self._run_adb(['devices', '-l'])
        devices = []
        
        for line in result.stdout.strip().split('\n')[1:]:  # Skip header
            if not line.strip():
                continue
            
            # Parse device line
            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                state = parts[1]
                
                # Parse additional info
                info = {}
                for part in parts[2:]:
                    if ':' in part:
                        key, value = part.split(':', 1)
                        info[key] = value
                
                device = DeviceInfo(
                    serial=serial,
                    state=state,
                    product=info.get('product', ''),
                    model=info.get('model', ''),
                    device=info.get('device', ''),
                    transport_id=info.get('transport_id', ''),
                    usb_port=info.get('usb', '')
                )
                devices.append(device)
                self.logger.adb(f"Found device: {device.model} ({device.serial})")
        
        return devices
    
    def get_device_info(self) -> Dict[str, str]:
        """Get detailed information about the current device."""
        info = {}
        
        props = [
            ('model', 'ro.product.model'),
            ('brand', 'ro.product.brand'),
            ('manufacturer', 'ro.product.manufacturer'),
            ('android_version', 'ro.build.version.release'),
            ('sdk_version', 'ro.build.version.sdk'),
            ('device', 'ro.product.device'),
            ('build_id', 'ro.build.id'),
            ('serial', 'ro.serialno'),
        ]
        
        for name, prop in props:
            result = self._run_adb(['shell', 'getprop', prop])
            if result.returncode == 0:
                info[name] = result.stdout.strip()
        
        self.logger.phone(f"Device info: {info.get('brand', '')} {info.get('model', '')} (Android {info.get('android_version', '')})")
        return info
    
    def get_screen_size(self) -> Tuple[int, int]:
        """Get device screen size."""
        result = self._run_adb(['shell', 'wm', 'size'])
        match = re.search(r'(\d+)x(\d+)', result.stdout)
        if match:
            width, height = int(match.group(1)), int(match.group(2))
            self.logger.phone(f"Screen size: {width}x{height}")
            return width, height
        return 1080, 1920  # Default
    
    def tap(self, x: int, y: int, duration: int = 0) -> bool:
        """
        Tap at coordinates.
        
        Args:
            x: X coordinate
            y: Y coordinate
            duration: Duration in milliseconds (0 for normal tap)
        
        Returns:
            True if successful
        """
        if duration > 0:
            # Long press
            result = self._run_adb(['shell', 'input', 'swipe', str(x), str(y), str(x), str(y), str(duration)])
        else:
            result = self._run_adb(['shell', 'input', 'tap', str(x), str(y)])
        
        success = result.returncode == 0
        self.logger.adb(f"Tap at ({x}, {y})" + (f" for {duration}ms" if duration else ""), 
                       level='INFO' if success else 'ERROR')
        return success
    
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> bool:
        """
        Swipe from one point to another.
        
        Args:
            x1, y1: Start coordinates
            x2, y2: End coordinates
            duration: Duration in milliseconds
        
        Returns:
            True if successful
        """
        result = self._run_adb(['shell', 'input', 'swipe', str(x1), str(y1), str(x2), str(y2), str(duration)])
        success = result.returncode == 0
        self.logger.adb(f"Swipe from ({x1}, {y1}) to ({x2}, {y2}) in {duration}ms",
                       level='INFO' if success else 'ERROR')
        return success
    
    def scroll_up(self, amount: int = 500) -> bool:
        """Scroll up on screen."""
        width, height = self.get_screen_size()
        center_x = width // 2
        return self.swipe(center_x, height // 2, center_x, height // 2 - amount)
    
    def scroll_down(self, amount: int = 500) -> bool:
        """Scroll down on screen."""
        width, height = self.get_screen_size()
        center_x = width // 2
        return self.swipe(center_x, height // 2, center_x, height // 2 + amount)
    
    def input_text(self, text: str) -> bool:
        """
        Input text on device.
        
        Args:
            text: Text to input (spaces will be encoded)
        
        Returns:
            True if successful
        """
        # Escape special characters
        escaped_text = text.replace(' ', '%s').replace("'", "\\'").replace('"', '\\"')
        result = self._run_adb(['shell', 'input', 'text', escaped_text])
        success = result.returncode == 0
        self.logger.adb(f"Input text: {text[:50]}{'...' if len(text) > 50 else ''}",
                       level='INFO' if success else 'ERROR')
        return success
    
    def press_key(self, keycode: int) -> bool:
        """
        Press a key.
        
        Common keycodes:
        - 3: HOME
        - 4: BACK
        - 24: VOLUME_UP
        - 25: VOLUME_DOWN
        - 26: POWER
        - 66: ENTER
        - 82: MENU
        - 187: APP_SWITCH
        
        Args:
            keycode: Android keycode
        
        Returns:
            True if successful
        """
        result = self._run_adb(['shell', 'input', 'keyevent', str(keycode)])
        success = result.returncode == 0
        self.logger.adb(f"Press key: {keycode}", level='INFO' if success else 'ERROR')
        return success
    
    def press_home(self) -> bool:
        """Press HOME button."""
        return self.press_key(3)
    
    def press_back(self) -> bool:
        """Press BACK button."""
        return self.press_key(4)
    
    def press_enter(self) -> bool:
        """Press ENTER key."""
        return self.press_key(66)
    
    def press_menu(self) -> bool:
        """Press MENU button."""
        return self.press_key(82)
    
    def press_app_switch(self) -> bool:
        """Press APP_SWITCH button."""
        return self.press_key(187)
    
    def open_url(self, url: str) -> bool:
        """
        Open a URL in the default browser.
        
        Args:
            url: URL to open
        
        Returns:
            True if successful
        """
        result = self._run_adb([
            'shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', url
        ])
        success = result.returncode == 0
        self.logger.browser(f"Opening URL: {url}", level='INFO' if success else 'ERROR')
        return success
    
    def launch_app(self, package: str, activity: Optional[str] = None) -> bool:
        """
        Launch an app.
        
        Args:
            package: Package name (e.g., 'com.brave.browser')
            activity: Activity name (optional)
        
        Returns:
            True if successful
        """
        if activity:
            component = f"{package}/{activity}"
            result = self._run_adb(['shell', 'am', 'start', '-n', component])
        else:
            result = self._run_adb(['shell', 'monkey', '-p', package, '-c', 
                                   'android.intent.category.LAUNCHER', '1'])
        
        success = result.returncode == 0
        self.logger.phone(f"Launching app: {package}", level='INFO' if success else 'ERROR')
        return success
    
    def stop_app(self, package: str) -> bool:
        """Stop an app."""
        result = self._run_adb(['shell', 'am', 'force-stop', package])
        success = result.returncode == 0
        self.logger.phone(f"Stopping app: {package}", level='INFO' if success else 'ERROR')
        return success
    
    def is_app_running(self, package: str) -> bool:
        """Check if an app is running."""
        result = self._run_adb(['shell', 'pidof', package])
        return result.returncode == 0 and result.stdout.strip()
    
    def get_current_activity(self) -> Optional[str]:
        """Get the current foreground activity."""
        result = self._run_adb(['shell', 'dumpsys', 'activity', 'activities', '|', 'grep', 'mResumedActivity'])
        if result.returncode == 0:
            match = re.search(r'(\S+/\S+)', result.stdout)
            if match:
                activity = match.group(1)
                self.logger.phone(f"Current activity: {activity}", level='DEBUG')
                return activity
        return None
    
    def screenshot(self, save_path: Optional[str] = None) -> Optional[str]:
        """
        Take a screenshot.
        
        Args:
            save_path: Path to save screenshot. If None, saves to ./phone/screenshots/
        
        Returns:
            Path to saved screenshot
        """
        if not save_path:
            screenshots_dir = Path(__file__).parent / 'screenshots'
            screenshots_dir.mkdir(exist_ok=True)
            save_path = screenshots_dir / f"screenshot_{int(time.time())}.png"
        
        # Take screenshot on device
        device_path = '/sdcard/screenshot_temp.png'
        self._run_adb(['shell', 'screencap', '-p', device_path])
        
        # Pull to local
        result = self._run_adb(['pull', device_path, str(save_path)])
        
        # Clean up device
        self._run_adb(['shell', 'rm', device_path])
        
        if result.returncode == 0:
            self.logger.phone(f"Screenshot saved: {save_path}")
            return str(save_path)
        return None
    
    def get_installed_packages(self) -> List[str]:
        """Get list of installed packages."""
        result = self._run_adb(['shell', 'pm', 'list', 'packages'])
        packages = []
        for line in result.stdout.strip().split('\n'):
            if line.startswith('package:'):
                packages.append(line.replace('package:', ''))
        return packages
    
    def install_apk(self, apk_path: str) -> bool:
        """Install an APK."""
        result = self._run_adb(['install', '-r', apk_path])
        success = result.returncode == 0
        self.logger.phone(f"Installing APK: {apk_path}", level='INFO' if success else 'ERROR')
        return success
    
    def uninstall_app(self, package: str) -> bool:
        """Uninstall an app."""
        result = self._run_adb(['uninstall', package])
        success = result.returncode == 0
        self.logger.phone(f"Uninstalling: {package}", level='INFO' if success else 'ERROR')
        return success
    
    def shell(self, command: str) -> str:
        """
        Execute a shell command on device.
        
        Args:
            command: Shell command to execute
        
        Returns:
            Command output
        """
        result = self._run_adb(['shell', command])
        return result.stdout.strip()
    
    def push_file(self, local_path: str, remote_path: str) -> bool:
        """Push a file to device."""
        result = self._run_adb(['push', local_path, remote_path])
        success = result.returncode == 0
        self.logger.adb(f"Push: {local_path} -> {remote_path}", level='INFO' if success else 'ERROR')
        return success
    
    def pull_file(self, remote_path: str, local_path: str) -> bool:
        """Pull a file from device."""
        result = self._run_adb(['pull', remote_path, local_path])
        success = result.returncode == 0
        self.logger.adb(f"Pull: {remote_path} -> {local_path}", level='INFO' if success else 'ERROR')
        return success
    
    def get_battery_info(self) -> Dict[str, Any]:
        """Get battery information."""
        result = self._run_adb(['shell', 'dumpsys', 'battery'])
        info = {}
        for line in result.stdout.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                info[key.strip()] = value.strip()
        return info
    
    def get_wifi_info(self) -> Dict[str, str]:
        """Get WiFi connection info."""
        result = self._run_adb(['shell', 'dumpsys', 'wifi', '|', 'grep', 'mWifiInfo'])
        return {'raw': result.stdout.strip()}
    
    def enable_wifi(self) -> bool:
        """Enable WiFi."""
        result = self._run_adb(['shell', 'svc', 'wifi', 'enable'])
        return result.returncode == 0
    
    def disable_wifi(self) -> bool:
        """Disable WiFi."""
        result = self._run_adb(['shell', 'svc', 'wifi', 'disable'])
        return result.returncode == 0
    
    def get_ip_address(self) -> Optional[str]:
        """Get device IP address."""
        result = self._run_adb(['shell', 'ip', 'addr', 'show', 'wlan0'])
        match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)
        if match:
            return match.group(1)
        return None
    
    def start_logcat(self, filter_spec: str = '*:V') -> subprocess.Popen:
        """
        Start logcat streaming.
        
        Args:
            filter_spec: Logcat filter specification
        
        Returns:
            Popen process for reading output
        """
        cmd = [self.adb_path]
        if self.device_serial:
            cmd.extend(['-s', self.device_serial])
        cmd.extend(['logcat', '-v', 'time', filter_spec])
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.logger.adb("Started logcat streaming")
        return process
    
    def clear_logcat(self) -> bool:
        """Clear logcat buffer."""
        result = self._run_adb(['logcat', '-c'])
        return result.returncode == 0
    
    def wait_for_device(self, timeout: int = 60) -> bool:
        """Wait for device to be available."""
        self.logger.adb(f"Waiting for device (timeout: {timeout}s)...")
        result = self._run_adb(['wait-for-device'], timeout=timeout)
        return result.returncode == 0
    
    def reboot(self, mode: str = '') -> bool:
        """
        Reboot device.
        
        Args:
            mode: '' for normal reboot, 'bootloader', 'recovery', 'sideload'
        """
        args = ['reboot']
        if mode:
            args.append(mode)
        result = self._run_adb(args)
        return result.returncode == 0


# Keycodes for convenience
class KeyCodes:
    """Android key codes."""
    HOME = 3
    BACK = 4
    CALL = 5
    END_CALL = 6
    VOLUME_UP = 24
    VOLUME_DOWN = 25
    POWER = 26
    CAMERA = 27
    CLEAR = 28
    ENTER = 66
    DELETE = 67
    MENU = 82
    SEARCH = 84
    MEDIA_PLAY_PAUSE = 85
    MEDIA_STOP = 86
    MEDIA_NEXT = 87
    MEDIA_PREVIOUS = 88
    MOVE_HOME = 122
    MOVE_END = 123
    APP_SWITCH = 187
    SLEEP = 223
    WAKEUP = 224
