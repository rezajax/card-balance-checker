"""
Phone Logger Module
===================
Comprehensive logging system for phone automation.
Logs ADB commands, phone events, browser activity, and more.
"""

import logging
import sys
import os
from datetime import datetime
from typing import Optional, Callable
from pathlib import Path
import threading
import queue
import json


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for terminal output."""
    
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'ADB': '\033[94m',        # Light Blue
        'PHONE': '\033[95m',      # Light Magenta
        'BROWSER': '\033[96m',    # Light Cyan
        'SCRCPY': '\033[92m',     # Light Green
    }
    RESET = '\033[0m'
    
    def format(self, record):
        # Add custom color based on log type
        log_type = getattr(record, 'log_type', record.levelname)
        color = self.COLORS.get(log_type, self.COLORS.get(record.levelname, ''))
        
        # Format timestamp
        record.timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        
        # Create formatted message
        formatted = super().format(record)
        return f"{color}{formatted}{self.RESET}"


class PhoneLogger:
    """
    Comprehensive logging system for phone automation.
    
    Features:
    - Multiple log categories (ADB, Phone, Browser, Scrcpy)
    - File and console logging
    - Real-time log streaming
    - Log history storage
    - JSON export capability
    """
    
    def __init__(self, log_dir: Optional[str] = None, max_history: int = 1000):
        """
        Initialize the phone logger.
        
        Args:
            log_dir: Directory for log files. Defaults to ./phone/logs/
            max_history: Maximum number of log entries to keep in memory
        """
        self.log_dir = Path(log_dir) if log_dir else Path(__file__).parent / 'logs'
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_history = max_history
        self.log_history = []
        self.log_queue = queue.Queue()
        self.callbacks = []
        self._lock = threading.Lock()
        
        # Create main logger
        self.logger = logging.getLogger('PhoneAutomation')
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers = []  # Clear existing handlers
        
        # Console handler with colors
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = ColoredFormatter(
            '%(timestamp)s | %(log_type)-8s | %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler for all logs
        log_file = self.log_dir / f"phone_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s | %(log_type)-8s | %(levelname)-8s | %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # Separate log files for each category
        self.category_handlers = {}
        for category in ['adb', 'phone', 'browser', 'scrcpy']:
            cat_file = self.log_dir / f"{category}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            cat_handler = logging.FileHandler(cat_file, encoding='utf-8')
            cat_handler.setLevel(logging.DEBUG)
            cat_handler.setFormatter(file_formatter)
            self.category_handlers[category] = cat_handler
        
        self.log('SYSTEM', 'INFO', 'Phone Logger initialized')
    
    def _log_internal(self, log_type: str, level: str, message: str, extra: Optional[dict] = None):
        """Internal logging method."""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'type': log_type,
            'level': level,
            'message': message,
            'extra': extra or {}
        }
        
        # Add to history
        with self._lock:
            self.log_history.append(log_entry)
            if len(self.log_history) > self.max_history:
                self.log_history.pop(0)
        
        # Add to queue for real-time streaming
        self.log_queue.put(log_entry)
        
        # Call registered callbacks
        for callback in self.callbacks:
            try:
                callback(log_entry)
            except Exception as e:
                pass  # Don't let callback errors affect logging
        
        # Log to main logger
        record = logging.LogRecord(
            name='PhoneAutomation',
            level=getattr(logging, level.upper(), logging.INFO),
            pathname='',
            lineno=0,
            msg=message,
            args=(),
            exc_info=None
        )
        record.log_type = log_type
        self.logger.handle(record)
        
        # Log to category-specific file
        category = log_type.lower()
        if category in self.category_handlers:
            self.category_handlers[category].emit(record)
    
    def log(self, log_type: str, level: str, message: str, extra: Optional[dict] = None):
        """
        Log a message.
        
        Args:
            log_type: Type of log (ADB, PHONE, BROWSER, SCRCPY, SYSTEM)
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: Log message
            extra: Additional data to include
        """
        self._log_internal(log_type, level, message, extra)
    
    def adb(self, message: str, level: str = 'INFO', extra: Optional[dict] = None):
        """Log ADB-related message."""
        self.log('ADB', level, message, extra)
    
    def phone(self, message: str, level: str = 'INFO', extra: Optional[dict] = None):
        """Log phone-related message."""
        self.log('PHONE', level, message, extra)
    
    def browser(self, message: str, level: str = 'INFO', extra: Optional[dict] = None):
        """Log browser-related message."""
        self.log('BROWSER', level, message, extra)
    
    def scrcpy(self, message: str, level: str = 'INFO', extra: Optional[dict] = None):
        """Log scrcpy-related message."""
        self.log('SCRCPY', level, message, extra)
    
    def debug(self, message: str, log_type: str = 'SYSTEM'):
        """Log debug message."""
        self.log(log_type, 'DEBUG', message)
    
    def info(self, message: str, log_type: str = 'SYSTEM'):
        """Log info message."""
        self.log(log_type, 'INFO', message)
    
    def warning(self, message: str, log_type: str = 'SYSTEM'):
        """Log warning message."""
        self.log(log_type, 'WARNING', message)
    
    def error(self, message: str, log_type: str = 'SYSTEM'):
        """Log error message."""
        self.log(log_type, 'ERROR', message)
    
    def critical(self, message: str, log_type: str = 'SYSTEM'):
        """Log critical message."""
        self.log(log_type, 'CRITICAL', message)
    
    def register_callback(self, callback: Callable):
        """Register a callback for real-time log streaming."""
        self.callbacks.append(callback)
    
    def unregister_callback(self, callback: Callable):
        """Unregister a callback."""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    def get_history(self, count: Optional[int] = None, log_type: Optional[str] = None) -> list:
        """
        Get log history.
        
        Args:
            count: Number of entries to return (None for all)
            log_type: Filter by log type
        
        Returns:
            List of log entries
        """
        with self._lock:
            history = self.log_history.copy()
        
        if log_type:
            history = [h for h in history if h['type'] == log_type]
        
        if count:
            history = history[-count:]
        
        return history
    
    def export_json(self, filepath: Optional[str] = None) -> str:
        """Export log history to JSON file."""
        if not filepath:
            filepath = self.log_dir / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.log_history, f, indent=2, ensure_ascii=False)
        
        return str(filepath)
    
    def clear_history(self):
        """Clear log history."""
        with self._lock:
            self.log_history.clear()
    
    def format_for_display(self, entry: dict) -> str:
        """Format a log entry for display."""
        timestamp = entry['timestamp'].split('T')[1][:12]
        return f"[{timestamp}] [{entry['type']:<8}] [{entry['level']:<8}] {entry['message']}"


# Global logger instance
_global_logger: Optional[PhoneLogger] = None

def get_logger() -> PhoneLogger:
    """Get the global logger instance."""
    global _global_logger
    if _global_logger is None:
        _global_logger = PhoneLogger()
    return _global_logger

def set_logger(logger: PhoneLogger):
    """Set the global logger instance."""
    global _global_logger
    _global_logger = logger
