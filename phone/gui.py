#!/usr/bin/env python3
"""
Phone Automation GUI
====================
Rich terminal-based GUI for phone automation with live logging.
"""

import sys
import os
import time
import threading
import queue
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

# Try to import rich for better UI
try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich.live import Live
    from rich.text import Text
    from rich.style import Style
    from rich.columns import Columns
    from rich.progress import Progress, SpinnerColumn, TextColumn
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Rich library not available. Install with: pip install rich")

sys.path.insert(0, str(Path(__file__).parent.parent))

from phone.adb_controller import ADBController
from phone.scrcpy_manager import ScrcpyManager, ScrcpyPresets
from phone.browser_automation import PhoneBrowserAutomation
from phone.logger import PhoneLogger, get_logger, set_logger


class LogPanel:
    """Panel for displaying logs."""
    
    def __init__(self, title: str, max_lines: int = 20, log_type: Optional[str] = None):
        self.title = title
        self.max_lines = max_lines
        self.log_type = log_type
        self.lines: List[Dict] = []
        self._lock = threading.Lock()
    
    def add_log(self, entry: Dict):
        """Add a log entry."""
        # Filter by type if specified
        if self.log_type and entry.get('type') != self.log_type:
            return
        
        with self._lock:
            self.lines.append(entry)
            if len(self.lines) > self.max_lines:
                self.lines.pop(0)
    
    def render(self) -> Panel:
        """Render the panel."""
        if not RICH_AVAILABLE:
            return None
        
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Time", style="dim", width=12)
        table.add_column("Level", width=8)
        table.add_column("Message")
        
        with self._lock:
            for entry in self.lines:
                # Format timestamp
                ts = entry['timestamp'].split('T')[1][:12] if 'T' in entry['timestamp'] else entry['timestamp']
                
                # Color by level
                level = entry.get('level', 'INFO')
                level_style = {
                    'DEBUG': 'dim',
                    'INFO': 'green',
                    'WARNING': 'yellow',
                    'ERROR': 'red',
                    'CRITICAL': 'red bold',
                }.get(level, 'white')
                
                table.add_row(
                    ts,
                    Text(level, style=level_style),
                    entry['message'][:80]
                )
        
        return Panel(table, title=f"[bold]{self.title}[/bold]", border_style="blue")


class PhoneAutomationGUI:
    """
    Rich terminal GUI for phone automation.
    
    Layout:
    ┌────────────────────────────────────────────────────────────┐
    │                    PHONE AUTOMATION                         │
    ├──────────────────────────────┬─────────────────────────────┤
    │     DEVICE INFO              │     SCRCPY STATUS           │
    ├──────────────────────────────┴─────────────────────────────┤
    │                      ALL LOGS                              │
    ├────────────────────────────────────────────────────────────┤
    │  ADB LOGS           │  PHONE LOGS        │  BROWSER LOGS   │
    └────────────────────────────────────────────────────────────┘
    """
    
    def __init__(self, device_serial: Optional[str] = None, screen_width: int = 1920):
        self.console = Console() if RICH_AVAILABLE else None
        
        # Initialize logger
        self.logger = PhoneLogger()
        set_logger(self.logger)
        
        # Register callback for log updates
        self.logger.register_callback(self._on_log)
        
        # Initialize components
        self.adb = ADBController(device_serial=device_serial, logger=self.logger)
        self.scrcpy = ScrcpyManager(device_serial=self.adb.device_serial, logger=self.logger)
        self.browser: Optional[PhoneBrowserAutomation] = None
        
        self.screen_width = screen_width
        self._running = True
        self._logcat_process = None
        
        # Create log panels
        self.all_logs = LogPanel("ALL LOGS", max_lines=15)
        self.adb_logs = LogPanel("ADB", max_lines=8, log_type='ADB')
        self.phone_logs = LogPanel("PHONE", max_lines=8, log_type='PHONE')
        self.browser_logs = LogPanel("BROWSER", max_lines=8, log_type='BROWSER')
        self.scrcpy_logs = LogPanel("SCRCPY", max_lines=8, log_type='SCRCPY')
        self.logcat_logs = LogPanel("LOGCAT", max_lines=10, log_type='LOGCAT')
        
        # Device info
        self.device_info = {}
        self._load_device_info()
    
    def _on_log(self, entry: Dict):
        """Callback for log updates."""
        self.all_logs.add_log(entry)
        self.adb_logs.add_log(entry)
        self.phone_logs.add_log(entry)
        self.browser_logs.add_log(entry)
        self.scrcpy_logs.add_log(entry)
        self.logcat_logs.add_log(entry)
    
    def _load_device_info(self):
        """Load device information."""
        try:
            self.device_info = self.adb.get_device_info()
        except Exception as e:
            self.device_info = {'error': str(e)}
    
    def _render_device_info(self) -> Panel:
        """Render device info panel."""
        if not RICH_AVAILABLE:
            return None
        
        table = Table(show_header=False, box=None)
        table.add_column("Property", style="cyan")
        table.add_column("Value")
        
        table.add_row("Model", f"{self.device_info.get('brand', '')} {self.device_info.get('model', '')}")
        table.add_row("Android", self.device_info.get('android_version', 'N/A'))
        table.add_row("SDK", self.device_info.get('sdk_version', 'N/A'))
        table.add_row("Serial", self.adb.device_serial or 'N/A')
        
        return Panel(table, title="[bold]📱 DEVICE[/bold]", border_style="green")
    
    def _render_scrcpy_status(self) -> Panel:
        """Render scrcpy status panel."""
        if not RICH_AVAILABLE:
            return None
        
        status = "🟢 Running" if self.scrcpy.is_running() else "🔴 Stopped"
        pid = self.scrcpy.get_pid() or "N/A"
        
        table = Table(show_header=False, box=None)
        table.add_column("Property", style="cyan")
        table.add_column("Value")
        
        table.add_row("Status", status)
        table.add_row("PID", str(pid))
        table.add_row("Resolution", str(self.scrcpy.config.max_size))
        table.add_row("FPS", str(self.scrcpy.config.max_fps))
        
        return Panel(table, title="[bold]🖥️ SCRCPY[/bold]", border_style="magenta")
    
    def _render_layout(self) -> Layout:
        """Render the full layout."""
        if not RICH_AVAILABLE:
            return None
        
        layout = Layout()
        
        # Main structure
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="top", size=8),
            Layout(name="main", size=12),
            Layout(name="bottom", size=12),
        )
        
        # Header
        layout["header"].update(
            Panel(
                Text("📱 PHONE AUTOMATION SYSTEM", justify="center", style="bold white on blue"),
                border_style="blue"
            )
        )
        
        # Top row - device info and scrcpy status
        layout["top"].split_row(
            Layout(name="device"),
            Layout(name="scrcpy"),
        )
        layout["device"].update(self._render_device_info())
        layout["scrcpy"].update(self._render_scrcpy_status())
        
        # Main - All logs
        layout["main"].update(self.all_logs.render())
        
        # Bottom - Category logs
        layout["bottom"].split_row(
            Layout(name="adb"),
            Layout(name="phone"),
            Layout(name="browser"),
        )
        layout["adb"].update(self.adb_logs.render())
        layout["phone"].update(self.phone_logs.render())
        layout["browser"].update(self.browser_logs.render())
        
        return layout
    
    def start_scrcpy(self, preset: str = 'right_panel') -> bool:
        """Start scrcpy."""
        if preset == 'right_panel':
            config = ScrcpyPresets.right_panel(self.screen_width)
        else:
            config = ScrcpyPresets.high_quality()
        return self.scrcpy.start(config)
    
    def stop_scrcpy(self) -> bool:
        """Stop scrcpy."""
        return self.scrcpy.stop()
    
    def init_browser(self, browser: str = 'brave') -> PhoneBrowserAutomation:
        """Initialize browser."""
        self.browser = PhoneBrowserAutomation(self.adb, browser=browser, logger=self.logger)
        return self.browser
    
    def start_logcat(self, filter_tags: Optional[List[str]] = None):
        """Start logcat streaming."""
        if filter_tags:
            filter_spec = ' '.join([f'{tag}:V' for tag in filter_tags]) + ' *:S'
        else:
            filter_spec = '*:I'
        
        self._logcat_process = self.adb.start_logcat(filter_spec)
        
        def read_logcat():
            while self._running and self._logcat_process and self._logcat_process.poll() is None:
                try:
                    line = self._logcat_process.stdout.readline()
                    if line:
                        line = line.strip()
                        if line:
                            level = 'DEBUG'
                            if ' E ' in line:
                                level = 'ERROR'
                            elif ' W ' in line:
                                level = 'WARNING'
                            elif ' I ' in line:
                                level = 'INFO'
                            self.logger.log('LOGCAT', level, line[:150])
                except:
                    break
        
        threading.Thread(target=read_logcat, daemon=True).start()
    
    def stop_logcat(self):
        """Stop logcat."""
        if self._logcat_process:
            self._logcat_process.terminate()
            self._logcat_process = None
    
    def open_url(self, url: str) -> bool:
        """Open URL in browser."""
        if not self.browser:
            self.init_browser()
        return self.browser.open_url(url)
    
    def run(self, url: Optional[str] = None):
        """Run the GUI."""
        if not RICH_AVAILABLE:
            print("Rich library required for GUI. Running in simple mode...")
            self._run_simple(url)
            return
        
        # Start scrcpy
        self.start_scrcpy()
        time.sleep(2)
        
        # Init browser
        self.init_browser('brave')
        
        # Start logcat
        self.start_logcat(['chromium', 'Brave', 'WebView'])
        
        # Open URL if specified
        if url:
            time.sleep(1)
            self.open_url(url)
        
        # Run live display
        try:
            with Live(self._render_layout(), refresh_per_second=2, console=self.console) as live:
                while self._running:
                    live.update(self._render_layout())
                    time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.cleanup()
    
    def _run_simple(self, url: Optional[str] = None):
        """Run in simple mode without rich."""
        print("\n" + "=" * 60)
        print("PHONE AUTOMATION SYSTEM")
        print("=" * 60)
        
        # Start scrcpy
        print("\n[Starting scrcpy...]")
        self.start_scrcpy()
        time.sleep(2)
        
        # Init browser
        print("[Initializing browser...]")
        self.init_browser('brave')
        
        # Start logcat
        print("[Starting logcat...]")
        self.start_logcat()
        
        # Open URL
        if url:
            print(f"[Opening {url}...]")
            self.open_url(url)
        
        print("\n[Running... Press Ctrl+C to stop]\n")
        
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources."""
        self._running = False
        self.stop_logcat()
        self.stop_scrcpy()
        print("\n[Cleaned up]")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Phone Automation GUI')
    parser.add_argument('--url', type=str, default='https://browserleaks.com',
                       help='URL to open (default: browserleaks.com)')
    parser.add_argument('--browser', type=str, default='brave',
                       choices=['brave', 'chrome', 'firefox'],
                       help='Browser to use')
    parser.add_argument('--device', type=str, help='Device serial')
    parser.add_argument('--screen-width', type=int, default=1920,
                       help='Screen width for positioning')
    parser.add_argument('--no-gui', action='store_true', help='Run without GUI')
    
    args = parser.parse_args()
    
    gui = PhoneAutomationGUI(
        device_serial=args.device,
        screen_width=args.screen_width
    )
    gui.run(url=args.url)


if __name__ == '__main__':
    main()
