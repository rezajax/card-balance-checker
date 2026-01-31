"""
Scrcpy Manager Module
=====================
Manage scrcpy for Android screen mirroring and control.
"""

import subprocess
import os
import signal
import time
import threading
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path

from .logger import PhoneLogger, get_logger


@dataclass
class ScrcpyConfig:
    """Configuration for scrcpy."""
    # Video settings
    max_size: int = 1024  # Max dimension (height or width)
    max_fps: int = 60
    video_codec: str = 'h265'  # h264, h265, av1
    video_bit_rate: str = '8M'
    
    # Audio settings
    no_audio: bool = False
    audio_codec: str = 'opus'  # opus, aac, flac, raw
    
    # Window settings
    window_title: str = 'Phone'
    window_x: Optional[int] = None
    window_y: Optional[int] = None
    window_width: Optional[int] = None
    window_height: Optional[int] = None
    window_borderless: bool = False
    always_on_top: bool = True
    fullscreen: bool = False
    
    # Control settings
    keyboard: str = 'uhid'  # disabled, sdk, uhid, aoa
    mouse: str = 'uhid'  # disabled, sdk, uhid, aoa
    no_control: bool = False
    
    # Display settings
    stay_awake: bool = True
    turn_screen_off: bool = False
    show_touches: bool = False
    
    # Recording
    record: Optional[str] = None
    record_format: str = 'mp4'  # mp4, mkv
    
    # Extra options
    extra_args: List[str] = field(default_factory=list)


class ScrcpyManager:
    """
    Manager for scrcpy screen mirroring.
    
    Features:
    - Start/stop scrcpy
    - Configure video/audio settings
    - Window positioning
    - Recording
    - Multi-device support
    """
    
    def __init__(self, device_serial: Optional[str] = None, logger: Optional[PhoneLogger] = None):
        """
        Initialize Scrcpy Manager.
        
        Args:
            device_serial: Device serial to mirror
            logger: Logger instance
        """
        self.logger = logger or get_logger()
        self.device_serial = device_serial
        self.scrcpy_path = self._find_scrcpy()
        self.process: Optional[subprocess.Popen] = None
        self.config = ScrcpyConfig()
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        
        if not self.scrcpy_path:
            self.logger.scrcpy("scrcpy not found!", level='ERROR')
            raise RuntimeError("scrcpy not found. Please install scrcpy.")
        
        self.logger.scrcpy(f"scrcpy found at: {self.scrcpy_path}")
    
    def _find_scrcpy(self) -> Optional[str]:
        """Find scrcpy executable."""
        try:
            result = subprocess.run(['which', 'scrcpy'], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        
        common_paths = [
            '/usr/bin/scrcpy',
            '/usr/local/bin/scrcpy',
            os.path.expanduser('~/bin/scrcpy'),
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def _build_command(self) -> List[str]:
        """Build scrcpy command with current configuration."""
        cmd = [self.scrcpy_path]
        
        # Device selection
        if self.device_serial:
            cmd.extend(['-s', self.device_serial])
        
        # Video settings
        if self.config.max_size:
            cmd.extend(['-m', str(self.config.max_size)])
        if self.config.max_fps:
            cmd.extend(['--max-fps', str(self.config.max_fps)])
        if self.config.video_codec:
            cmd.extend(['--video-codec', self.config.video_codec])
        if self.config.video_bit_rate:
            cmd.extend(['--video-bit-rate', self.config.video_bit_rate])
        
        # Audio settings
        if self.config.no_audio:
            cmd.append('--no-audio')
        elif self.config.audio_codec:
            cmd.extend(['--audio-codec', self.config.audio_codec])
        
        # Window settings
        if self.config.window_title:
            cmd.extend(['--window-title', self.config.window_title])
        if self.config.window_x is not None:
            cmd.extend(['--window-x', str(self.config.window_x)])
        if self.config.window_y is not None:
            cmd.extend(['--window-y', str(self.config.window_y)])
        if self.config.window_width:
            cmd.extend(['--window-width', str(self.config.window_width)])
        if self.config.window_height:
            cmd.extend(['--window-height', str(self.config.window_height)])
        if self.config.window_borderless:
            cmd.append('--window-borderless')
        if self.config.always_on_top:
            cmd.append('--always-on-top')
        if self.config.fullscreen:
            cmd.append('--fullscreen')
        
        # Control settings
        if self.config.no_control:
            cmd.append('--no-control')
        else:
            if self.config.keyboard:
                cmd.extend(['--keyboard', self.config.keyboard])
            if self.config.mouse:
                cmd.extend(['--mouse', self.config.mouse])
        
        # Display settings
        if self.config.stay_awake:
            cmd.append('--stay-awake')
        if self.config.turn_screen_off:
            cmd.append('--turn-screen-off')
        if self.config.show_touches:
            cmd.append('--show-touches')
        
        # Recording
        if self.config.record:
            cmd.extend(['--record', self.config.record])
            cmd.extend(['--record-format', self.config.record_format])
        
        # Extra args
        cmd.extend(self.config.extra_args)
        
        return cmd
    
    def start(self, config: Optional[ScrcpyConfig] = None) -> bool:
        """
        Start scrcpy.
        
        Args:
            config: Optional configuration override
        
        Returns:
            True if started successfully
        """
        if self.is_running():
            self.logger.scrcpy("scrcpy is already running", level='WARNING')
            return True
        
        if config:
            self.config = config
        
        cmd = self._build_command()
        cmd_str = ' '.join(cmd)
        self.logger.scrcpy(f"Starting: {cmd_str}")
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self._running = True
            self._monitor_thread = threading.Thread(target=self._monitor_process, daemon=True)
            self._monitor_thread.start()
            
            # Wait a bit to check if it started successfully
            time.sleep(1)
            
            if self.process.poll() is None:
                self.logger.scrcpy(f"Started successfully (PID: {self.process.pid})")
                return True
            else:
                stderr = self.process.stderr.read()
                self.logger.scrcpy(f"Failed to start: {stderr}", level='ERROR')
                return False
                
        except Exception as e:
            self.logger.scrcpy(f"Error starting scrcpy: {e}", level='ERROR')
            return False
    
    def _monitor_process(self):
        """Monitor scrcpy process output."""
        if not self.process:
            return
        
        while self._running and self.process.poll() is None:
            try:
                line = self.process.stderr.readline()
                if line:
                    self.logger.scrcpy(f"[stderr] {line.strip()}", level='DEBUG')
            except Exception:
                break
        
        if self.process.poll() is not None:
            self._running = False
            self.logger.scrcpy(f"Process ended with code: {self.process.returncode}")
    
    def stop(self) -> bool:
        """Stop scrcpy."""
        if not self.is_running():
            self.logger.scrcpy("scrcpy is not running")
            return True
        
        self._running = False
        
        try:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.logger.scrcpy("Stopped gracefully")
            return True
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.logger.scrcpy("Force killed")
            return True
        except Exception as e:
            self.logger.scrcpy(f"Error stopping: {e}", level='ERROR')
            return False
        finally:
            self.process = None
    
    def restart(self) -> bool:
        """Restart scrcpy."""
        self.stop()
        time.sleep(1)
        return self.start()
    
    def is_running(self) -> bool:
        """Check if scrcpy is running."""
        return self.process is not None and self.process.poll() is None
    
    def get_pid(self) -> Optional[int]:
        """Get scrcpy process ID."""
        if self.is_running():
            return self.process.pid
        return None
    
    def set_position(self, x: int, y: int) -> None:
        """Set window position (requires restart)."""
        self.config.window_x = x
        self.config.window_y = y
        self.logger.scrcpy(f"Window position set to ({x}, {y}) - restart required")
    
    def set_size(self, width: int, height: int) -> None:
        """Set window size (requires restart)."""
        self.config.window_width = width
        self.config.window_height = height
        self.logger.scrcpy(f"Window size set to {width}x{height} - restart required")
    
    def set_max_resolution(self, max_size: int) -> None:
        """Set max resolution (requires restart)."""
        self.config.max_size = max_size
        self.logger.scrcpy(f"Max resolution set to {max_size} - restart required")
    
    def set_fps(self, fps: int) -> None:
        """Set max FPS (requires restart)."""
        self.config.max_fps = fps
        self.logger.scrcpy(f"Max FPS set to {fps} - restart required")
    
    def enable_recording(self, output_path: str, format: str = 'mp4') -> None:
        """Enable recording (requires restart)."""
        self.config.record = output_path
        self.config.record_format = format
        self.logger.scrcpy(f"Recording enabled: {output_path}")
    
    def disable_recording(self) -> None:
        """Disable recording (requires restart)."""
        self.config.record = None
        self.logger.scrcpy("Recording disabled")
    
    def configure_for_right_side(self, screen_width: int = 1920) -> None:
        """
        Configure scrcpy window for right side of screen.
        
        Args:
            screen_width: Total screen width
        """
        # Calculate position for right side
        phone_width = 400  # Approximate phone window width
        margin = 20
        
        self.config.window_x = screen_width - phone_width - margin
        self.config.window_y = 50
        self.config.window_width = phone_width
        self.config.always_on_top = True
        self.config.window_borderless = False
        self.config.window_title = "📱 Phone"
        
        self.logger.scrcpy(f"Configured for right side at x={self.config.window_x}")
    
    @staticmethod
    def get_version() -> Optional[str]:
        """Get scrcpy version."""
        try:
            result = subprocess.run(['scrcpy', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                # First line contains version
                return result.stdout.strip().split('\n')[0]
        except Exception:
            pass
        return None


class ScrcpyPresets:
    """Preset configurations for common use cases."""
    
    @staticmethod
    def high_quality() -> ScrcpyConfig:
        """High quality preset."""
        return ScrcpyConfig(
            max_size=1920,
            max_fps=60,
            video_codec='h265',
            video_bit_rate='16M',
            no_audio=False,
            audio_codec='opus'
        )
    
    @staticmethod
    def low_latency() -> ScrcpyConfig:
        """Low latency preset."""
        return ScrcpyConfig(
            max_size=1024,
            max_fps=60,
            video_codec='h264',
            video_bit_rate='4M',
            no_audio=True
        )
    
    @staticmethod
    def battery_saver() -> ScrcpyConfig:
        """Battery saver preset."""
        return ScrcpyConfig(
            max_size=720,
            max_fps=30,
            video_codec='h264',
            video_bit_rate='2M',
            no_audio=True,
            turn_screen_off=True,
            stay_awake=True
        )
    
    @staticmethod
    def recording() -> ScrcpyConfig:
        """Recording preset."""
        return ScrcpyConfig(
            max_size=1920,
            max_fps=60,
            video_codec='h265',
            video_bit_rate='12M',
            no_audio=False,
            audio_codec='opus',
            record_format='mp4'
        )
    
    @staticmethod
    def right_panel(screen_width: int = 1920) -> ScrcpyConfig:
        """Right panel preset - optimized for side display."""
        phone_width = 380
        margin = 20
        
        return ScrcpyConfig(
            max_size=1024,
            max_fps=60,
            video_codec='h265',
            video_bit_rate='8M',
            no_audio=True,
            window_x=screen_width - phone_width - margin,
            window_y=50,
            window_width=phone_width,
            always_on_top=True,
            window_title='📱 Phone',
            stay_awake=True,
            keyboard='uhid',
            mouse='uhid'
        )
