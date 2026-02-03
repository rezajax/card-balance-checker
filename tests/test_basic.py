"""
Basic tests for Card Balance Checker
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestImports:
    """Test that all modules can be imported."""
    
    def test_import_stealth_browser(self):
        """Test stealth_browser module imports."""
        from stealth_browser import StealthBrowser
        assert StealthBrowser is not None
    
    def test_import_stealth_card_checker(self):
        """Test stealth_card_checker module imports."""
        from stealth_card_checker import StealthCardChecker
        assert StealthCardChecker is not None
    
    def test_import_sheets_manager(self):
        """Test sheets_manager module imports."""
        from sheets_manager import SheetsManager
        assert SheetsManager is not None


class TestSheetsManager:
    """Test SheetsManager functionality."""
    
    def test_initialization(self):
        """Test SheetsManager can be instantiated."""
        from sheets_manager import SheetsManager
        manager = SheetsManager(credentials_file='fake.json')
        assert manager is not None
        assert manager.credentials_file == 'fake.json'


class TestStealthBrowser:
    """Test StealthBrowser functionality."""
    
    def test_initialization(self):
        """Test StealthBrowser can be instantiated."""
        from stealth_browser import StealthBrowser
        browser = StealthBrowser(headless=True, timeout=30000)
        assert browser is not None
        assert browser.headless == True
        assert browser.timeout == 30  # Converted to seconds


class TestStealthCardChecker:
    """Test StealthCardChecker functionality."""
    
    def test_initialization(self):
        """Test StealthCardChecker can be instantiated."""
        from stealth_card_checker import StealthCardChecker
        checker = StealthCardChecker(headless=True, max_retries=3)
        assert checker is not None
        assert checker.headless == True
        assert checker.max_retries == 3
    
    def test_is_cancelled_default(self):
        """Test is_cancelled returns False by default."""
        from stealth_card_checker import StealthCardChecker
        checker = StealthCardChecker()
        assert checker.is_cancelled() == False
    
    def test_force_cancel(self):
        """Test force_cancel sets cancelled flag."""
        from stealth_card_checker import StealthCardChecker
        checker = StealthCardChecker()
        checker.force_cancel()
        assert checker._cancelled == True


class TestPhoneModules:
    """Test phone automation modules."""
    
    def test_import_adb_controller(self):
        """Test adb_controller can be imported."""
        from phone.adb_controller import ADBController
        assert ADBController is not None
    
    def test_import_phone_logger(self):
        """Test phone logger can be imported."""
        from phone.logger import PhoneLogger
        assert PhoneLogger is not None


# Placeholder for integration tests
class TestIntegration:
    """Integration tests (require external services)."""
    
    @pytest.mark.skip(reason="Requires Google Sheets credentials")
    def test_sheets_connection(self):
        """Test connecting to Google Sheets."""
        pass
    
    @pytest.mark.skip(reason="Requires browser installation")
    def test_browser_launch(self):
        """Test launching stealth browser."""
        pass
