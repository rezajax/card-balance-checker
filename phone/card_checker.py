#!/usr/bin/env python3
"""
Phone Card Checker - چک بالانس کارت روی گوشی
===========================================
این ماژول سایت rcbalance.com رو روی مرورگر گوشی باز میکنه و کارت رو چک میکنه.
"""

import time
import re
import threading
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .adb_controller import ADBController
from .browser_automation import PhoneBrowserAutomation
from .screen_reader import ScreenReader
from .logger import PhoneLogger, get_logger


class CheckStatus(Enum):
    """وضعیت چک کارت"""
    IDLE = "idle"
    STARTING = "starting"
    OPENING_SITE = "opening_site"
    FILLING_FORM = "filling_form"
    WAITING_CAPTCHA = "waiting_captcha"
    SOLVING_CAPTCHA = "solving_captcha"
    SUBMITTING = "submitting"
    WAITING_RESULT = "waiting_result"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CardInfo:
    """اطلاعات کارت"""
    card_number: str
    exp_month: str
    exp_year: str
    cvv: str
    
    def masked(self) -> str:
        """نمایش ماسک شده شماره کارت"""
        if len(self.card_number) > 8:
            return f"{self.card_number[:4]}****{self.card_number[-4:]}"
        return "****"


@dataclass
class CheckResult:
    """نتیجه چک کارت"""
    success: bool
    balance: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    check_date: str = field(default_factory=lambda: datetime.now().isoformat())
    cancelled: bool = False
    screenshots: List[str] = field(default_factory=list)


class PhoneCardChecker:
    """
    Card Checker برای گوشی
    
    این کلاس سایت rcbalance.com رو روی مرورگر گوشی باز میکنه،
    اطلاعات کارت رو وارد میکنه و نتیجه رو میخونه.
    """
    
    SITE_URL = "https://rcbalance.com"
    
    # Element patterns for finding fields
    FIELD_PATTERNS = {
        'card_number': ['card', 'number', '16', 'شماره'],
        'exp_month': ['month', 'mm', 'ماه'],
        'exp_year': ['year', 'yy', 'سال'],
        'cvv': ['cvv', 'cvc', 'security', 'امنیتی'],
    }
    
    def __init__(
        self,
        adb: ADBController,
        browser: PhoneBrowserAutomation,
        screen_reader: ScreenReader,
        logger: Optional[PhoneLogger] = None,
        status_callback: Optional[Callable[[str, int], None]] = None,
    ):
        """
        Args:
            adb: کنترلر ADB
            browser: اتوماسیون مرورگر
            screen_reader: خواننده صفحه
            logger: لاگر
            status_callback: تابع callback برای آپدیت وضعیت
        """
        self.adb = adb
        self.browser = browser
        self.screen_reader = screen_reader
        self.logger = logger or get_logger()
        self.status_callback = status_callback
        
        self._status = CheckStatus.IDLE
        self._progress = 0
        self._cancelled = False
        self._current_task: Optional[threading.Thread] = None
        self._last_result: Optional[CheckResult] = None
        
        # تنظیمات
        self.wait_timeout = 60  # حداکثر زمان انتظار برای CAPTCHA
        self.check_interval = 1.5  # فاصله بین چک‌ها
        self.screenshot_dir = "phone/screenshots"
    
    @property
    def status(self) -> CheckStatus:
        return self._status
    
    @property
    def progress(self) -> int:
        return self._progress
    
    @property
    def is_running(self) -> bool:
        return self._status not in [CheckStatus.IDLE, CheckStatus.COMPLETED, CheckStatus.FAILED, CheckStatus.CANCELLED]
    
    def update_status(self, status: CheckStatus, progress: int, message: str = ""):
        """آپدیت وضعیت"""
        self._status = status
        self._progress = progress
        
        log_msg = f"[{status.value}] {message}" if message else f"[{status.value}]"
        self.logger.info(log_msg, log_type='CARD')
        
        if self.status_callback:
            display_msg = message or status.value.replace('_', ' ').title()
            self.status_callback(display_msg, progress)
    
    def cancel(self):
        """لغو عملیات"""
        self._cancelled = True
        self.update_status(CheckStatus.CANCELLED, 0, "Operation cancelled by user")
    
    def is_cancelled(self) -> bool:
        return self._cancelled
    
    def check_balance(self, card: CardInfo) -> CheckResult:
        """
        چک بالانس کارت
        
        Args:
            card: اطلاعات کارت
            
        Returns:
            نتیجه چک
        """
        self._cancelled = False
        screenshots = []
        
        try:
            # شروع
            self.update_status(CheckStatus.STARTING, 5, f"Starting check for {card.masked()}")
            
            if self.is_cancelled():
                return CheckResult(success=False, error="Cancelled", cancelled=True)
            
            # باز کردن سایت
            self.update_status(CheckStatus.OPENING_SITE, 10, f"Opening {self.SITE_URL}")
            
            if not self.browser.open_url(self.SITE_URL):
                return CheckResult(success=False, error="Failed to open website")
            
            # صبر بیشتر برای لود کامل صفحه
            self.update_status(CheckStatus.OPENING_SITE, 15, "Waiting for page to load...")
            time.sleep(6)  # صبر بیشتر
            
            # بستن کیبورد اگر باز بود و کلیک روی صفحه برای خارج شدن از آدرس بار
            self.adb.press_back()
            time.sleep(0.5)
            
            # یک تپ روی وسط صفحه برای اطمینان از focus روی صفحه (نه آدرس بار)
            width, height = self.adb.get_screen_size()
            self.adb.tap(width // 2, height // 2)
            time.sleep(0.5)
            
            # یک اسکرول کوچک پایین برای اطمینان از دیدن فرم
            self.browser.scroll_down(200)
            time.sleep(1)
            
            self.update_status(CheckStatus.OPENING_SITE, 20, "Page loaded, preparing form...")
            
            # گرفتن اسکرین‌شات
            ss = self._take_screenshot("01_page_loaded")
            if ss:
                screenshots.append(ss)
            
            if self.is_cancelled():
                return CheckResult(success=False, error="Cancelled", cancelled=True, screenshots=screenshots)
            
            # پر کردن فرم
            self.update_status(CheckStatus.FILLING_FORM, 30, "Filling card information...")
            
            if not self._fill_card_form(card):
                return CheckResult(success=False, error="Failed to fill form", screenshots=screenshots)
            
            self.update_status(CheckStatus.FILLING_FORM, 50, "Form filled successfully")
            
            # گرفتن اسکرین‌شات
            ss = self._take_screenshot("02_form_filled")
            if ss:
                screenshots.append(ss)
            
            if self.is_cancelled():
                return CheckResult(success=False, error="Cancelled", cancelled=True, screenshots=screenshots)
            
            # Handle CAPTCHA
            self.update_status(CheckStatus.WAITING_CAPTCHA, 55, "Looking for CAPTCHA...")
            
            captcha_solved = self._handle_captcha()
            
            if not captcha_solved:
                # اگر CAPTCHA حل نشد، صبر میکنیم کاربر حل کنه
                self.update_status(CheckStatus.WAITING_CAPTCHA, 60, 
                                   f"Please solve CAPTCHA manually ({self.wait_timeout}s timeout)")
                
                if not self._wait_for_captcha_solved():
                    ss = self._take_screenshot("captcha_failed")
                    if ss:
                        screenshots.append(ss)
                    return CheckResult(success=False, error="CAPTCHA not solved", screenshots=screenshots)
            
            self.update_status(CheckStatus.SOLVING_CAPTCHA, 70, "CAPTCHA handled")
            
            # گرفتن اسکرین‌شات
            ss = self._take_screenshot("03_captcha_done")
            if ss:
                screenshots.append(ss)
            
            if self.is_cancelled():
                return CheckResult(success=False, error="Cancelled", cancelled=True, screenshots=screenshots)
            
            # Submit فرم
            self.update_status(CheckStatus.SUBMITTING, 75, "Submitting form...")
            
            if not self._submit_form():
                return CheckResult(success=False, error="Failed to submit form", screenshots=screenshots)
            
            # صبر برای نتیجه
            self.update_status(CheckStatus.WAITING_RESULT, 80, "Waiting for result...")
            time.sleep(4)
            
            # گرفتن اسکرین‌شات
            ss = self._take_screenshot("04_result")
            if ss:
                screenshots.append(ss)
            
            # خواندن نتیجه
            self.update_status(CheckStatus.EXTRACTING, 90, "Extracting balance...")
            result = self._extract_balance()
            result.screenshots = screenshots
            
            if result.success:
                self.update_status(CheckStatus.COMPLETED, 100, f"Balance: {result.balance}")
            else:
                self.update_status(CheckStatus.FAILED, 100, result.error or "Could not extract balance")
            
            self._last_result = result
            return result
            
        except Exception as e:
            self.logger.error(f"Error checking card: {e}", log_type='CARD')
            ss = self._take_screenshot("error")
            if ss:
                screenshots.append(ss)
            return CheckResult(success=False, error=str(e), screenshots=screenshots)
    
    def _take_screenshot(self, name: str) -> Optional[str]:
        """گرفتن اسکرین‌شات"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"card_check_{name}_{timestamp}.png"
            return self.browser.take_screenshot(filename)
        except Exception as e:
            self.logger.warning(f"Failed to take screenshot: {e}", log_type='CARD')
            return None
    
    def _fill_card_form(self, card: CardInfo) -> bool:
        """پر کردن فرم کارت"""
        try:
            width, height = self.adb.get_screen_size()
            self.logger.info(f"Screen size: {width}x{height}", log_type='CARD')
            
            # استفاده از روش پیدا کردن فیلدها
            return self._fill_fields_default(card, width, height)
            
        except Exception as e:
            self.logger.error(f"Error filling form: {e}", log_type='CARD')
            return False
    
    def _type_text_slowly(self, text: str, delay_per_char: float = 0.05) -> bool:
        """تایپ کردن متن به صورت کاراکتر به کاراکتر برای اطمینان از ورود کامل"""
        try:
            # برای متن‌های کوتاه (کمتر از 6 کاراکتر) یکجا بفرست
            if len(text) <= 5:
                self.adb.input_text(text)
                return True
            
            # برای متن‌های بلند، تکه تکه بفرست
            chunk_size = 4
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i+chunk_size]
                self.adb.input_text(chunk)
                time.sleep(delay_per_char * len(chunk))
            
            return True
        except Exception as e:
            self.logger.error(f"Error typing text: {e}", log_type='CARD')
            return False
    
    
    def _fill_fields_default(self, card: CardInfo, width: int, height: int) -> bool:
        """پر کردن فیلدها با موقعیت‌های پیش‌فرض"""
        try:
            center_x = width // 2
            
            self.logger.info("Using default field positions", log_type='CARD')
            
            # اول باید فیلدهای EditText رو پیدا کنیم
            editable_fields = self.screen_reader.find_editable() or []
            self.logger.info(f"Found {len(editable_fields)} editable fields on page", log_type='CARD')
            
            # اگر فیلدهای EditText پیدا شدن، از اونا استفاده کن
            if len(editable_fields) >= 1:
                # مرتب‌سازی بر اساس موقعیت Y
                sorted_fields = sorted(editable_fields, key=lambda f: f.y1)
                
                # لاگ همه فیلدها
                for i, f in enumerate(sorted_fields):
                    self.logger.info(f"Field {i}: center={f.center}, bounds=({f.x1},{f.y1})-({f.x2},{f.y2})", log_type='CARD')
                
                # اولین فیلد: شماره کارت
                if len(sorted_fields) >= 1:
                    field = sorted_fields[0]
                    x, y = field.center
                    self.logger.info(f"Tapping card number field at ({x}, {y})", log_type='CARD')
                    self.adb.tap(x, y)
                    time.sleep(1.0)
                    self._type_text_slowly(card.card_number)
                    time.sleep(0.5)
                    # بستن کیبورد
                    self.adb.press_back()
                    time.sleep(0.5)
                
                # دومین فیلد: ماه
                if len(sorted_fields) >= 2:
                    field = sorted_fields[1]
                    x, y = field.center
                    self.logger.info(f"Tapping exp month field at ({x}, {y})", log_type='CARD')
                    self.adb.tap(x, y)
                    time.sleep(0.7)
                    self.adb.input_text(card.exp_month)
                    time.sleep(0.3)
                
                # سومین فیلد: سال
                if len(sorted_fields) >= 3:
                    field = sorted_fields[2]
                    x, y = field.center
                    self.logger.info(f"Tapping exp year field at ({x}, {y})", log_type='CARD')
                    self.adb.tap(x, y)
                    time.sleep(0.7)
                    self.adb.input_text(card.exp_year)
                    time.sleep(0.3)
                
                # چهارمین فیلد: CVV
                if len(sorted_fields) >= 4:
                    field = sorted_fields[3]
                    x, y = field.center
                    self.logger.info(f"Tapping CVV field at ({x}, {y})", log_type='CARD')
                    self.adb.tap(x, y)
                    time.sleep(0.7)
                    self.adb.input_text(card.cvv)
                    time.sleep(0.3)
                
                # بستن کیبورد
                self.adb.press_back()
                time.sleep(0.5)
                
                self.logger.info("Form filling completed using detected fields", log_type='CARD')
                return True
            
            # اگر فیلدی پیدا نشد، خطا بده
            self.logger.error("No editable fields found on page!", log_type='CARD')
            return False
            
        except Exception as e:
            self.logger.error(f"Error filling default fields: {e}", log_type='CARD')
            return False
    
    def _handle_captcha(self) -> bool:
        """تلاش برای حل CAPTCHA"""
        try:
            # چک کردن وجود CAPTCHA در صفحه
            screen_text = self.screen_reader.get_all_text() or ""
            
            # اگر متن "I'm not a robot" یا checkbox پیدا شد
            if 'robot' in screen_text.lower() or 'recaptcha' in screen_text.lower():
                self.logger.info("CAPTCHA detected, looking for checkbox...", log_type='CARD')
                
                # تلاش برای کلیک روی checkbox
                checkbox = self.screen_reader.find_by_text("robot", exact=False)
                if checkbox:
                    elem = checkbox[0]
                    if elem.center:
                        self.adb.tap(elem.center[0], elem.center[1])
                        time.sleep(2)
                        return True
                
                # اگر checkbox پیدا نشد، کلیک در ناحیه معمول CAPTCHA
                width, height = self.adb.get_screen_size()
                captcha_y = int(height * 0.65)
                self.adb.tap(width // 2 - 150, captcha_y)
                time.sleep(2)
                
            return False
            
        except Exception as e:
            self.logger.debug(f"Error handling CAPTCHA: {e}", log_type='CARD')
            return False
    
    def _wait_for_captcha_solved(self) -> bool:
        """صبر کردن تا کاربر CAPTCHA رو حل کنه"""
        start_time = time.time()
        
        while time.time() - start_time < self.wait_timeout:
            if self.is_cancelled():
                return False
            
            # چک کردن وضعیت CAPTCHA
            screen_text = self.screen_reader.get_all_text() or ""
            
            # اگر متن نتیجه پیدا شد یا CAPTCHA نیست
            if any(word in screen_text.lower() for word in ['balance', 'بالانس', '$', 'invalid', 'error']):
                return True
            
            # اگر checkbox تیک خورده (checkmark visible)
            # این رو از تغییر محتوای صفحه تشخیص میدیم
            
            remaining = int(self.wait_timeout - (time.time() - start_time))
            if remaining % 10 == 0:
                self.update_status(CheckStatus.WAITING_CAPTCHA, 60, f"Waiting for CAPTCHA... ({remaining}s)")
            
            time.sleep(self.check_interval)
        
        return False
    
    def _submit_form(self) -> bool:
        """Submit کردن فرم"""
        try:
            # تلاش برای پیدا کردن دکمه submit
            submit_texts = ['check', 'submit', 'balance', 'بررسی', 'ارسال']
            
            for text in submit_texts:
                elements = self.screen_reader.find_by_text(text, exact=False)
                if elements:
                    for elem in elements:
                        if elem.clickable and elem.center:
                            self.adb.tap(elem.center[0], elem.center[1])
                            time.sleep(1)
                            return True
            
            # اگر دکمه پیدا نشد، Enter بزنیم
            self.adb.press_enter()
            time.sleep(1)
            
            # یا روی ناحیه معمول دکمه submit کلیک کنیم
            width, height = self.adb.get_screen_size()
            submit_y = int(height * 0.75)
            self.adb.tap(width // 2, submit_y)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error submitting form: {e}", log_type='CARD')
            return False
    
    def _extract_balance(self) -> CheckResult:
        """استخراج بالانس از صفحه نتیجه"""
        try:
            # صبر برای لود شدن نتیجه
            time.sleep(2)
            
            # خواندن متن صفحه
            screen_text = self.screen_reader.get_all_text() or ""
            
            # الگوهای بالانس
            balance_patterns = [
                r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',  # $1,234.56
                r'(\d+(?:\.\d{2})?)\s*(?:USD|dollars?)',  # 123.45 USD
                r'balance[:\s]*\$?\s*(\d+(?:\.\d{2})?)',  # balance: 123.45
                r'(\d+(?:\.\d{2})?)\s*(?:available)',  # 123.45 available
            ]
            
            for pattern in balance_patterns:
                matches = re.findall(pattern, screen_text, re.IGNORECASE)
                if matches:
                    balance = matches[0]
                    if not balance.startswith('$'):
                        balance = f"${balance}"
                    
                    self.logger.info(f"Balance found: {balance}", log_type='CARD')
                    return CheckResult(
                        success=True,
                        balance=balance,
                        message="Balance retrieved successfully"
                    )
            
            # چک کردن پیام‌های خطا
            error_patterns = [
                'invalid', 'error', 'failed', 'incorrect', 'not found',
                'نامعتبر', 'خطا', 'یافت نشد'
            ]
            
            for pattern in error_patterns:
                if pattern in screen_text.lower():
                    return CheckResult(
                        success=False,
                        error="Card validation failed or invalid card"
                    )
            
            # اگر چیزی پیدا نشد
            return CheckResult(
                success=False,
                error="Could not extract balance from page"
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting balance: {e}", log_type='CARD')
            return CheckResult(success=False, error=str(e))
    
    def check_balance_async(self, card: CardInfo, callback: Callable[[CheckResult], None] = None):
        """
        چک بالانس به صورت async (در thread جداگانه)
        
        Args:
            card: اطلاعات کارت
            callback: تابع callback برای دریافت نتیجه
        """
        def _run():
            result = self.check_balance(card)
            if callback:
                callback(result)
        
        self._current_task = threading.Thread(target=_run, daemon=True)
        self._current_task.start()
    
    def get_last_result(self) -> Optional[CheckResult]:
        """گرفتن آخرین نتیجه"""
        return self._last_result
    
    def get_status_dict(self) -> Dict[str, Any]:
        """گرفتن وضعیت به صورت dictionary"""
        return {
            'status': self._status.value,
            'progress': self._progress,
            'is_running': self.is_running,
            'last_result': {
                'success': self._last_result.success,
                'balance': self._last_result.balance,
                'error': self._last_result.error,
                'check_date': self._last_result.check_date,
            } if self._last_result else None
        }
