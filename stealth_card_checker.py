#!/usr/bin/env python3
"""
Stealth Card Checker - چک بالانس با مرورگر Stealth
این ورژن از SeleniumBase UC Mode استفاده می‌کنه که سیستم‌های anti-bot رو bypass می‌کنه.
"""

import time
import logging
from datetime import datetime
from typing import Callable, Dict, Any, Optional
from stealth_browser import StealthBrowser

logger = logging.getLogger(__name__)


class StealthCardChecker:
    """
    Card checker using SeleniumBase UC Mode for anti-bot bypass.
    این کلاس برای سایت‌هایی که Cloudflare/anti-bot دارن بهتر کار می‌کنه.
    """
    
    SITE_URL = "https://rcbalance.com"
    
    def __init__(
        self, 
        headless: bool = False,
        timeout: int = 60000,
        status_callback: Callable = None,
        max_retries: int = 5,
        cancel_check: Callable = None,
        captcha_mode: str = 'auto',
        gemini_settings: dict = None,
        **kwargs  # برای سازگاری با CardChecker
    ):
        """
        Args:
            headless: اجرا بدون نمایش مرورگر
            timeout: حداکثر زمان انتظار (میلی‌ثانیه)
            status_callback: تابع callback برای آپدیت وضعیت
            max_retries: حداکثر تلاش مجدد
            cancel_check: تابع بررسی cancel
            captcha_mode: حالت حل CAPTCHA
            gemini_settings: تنظیمات Gemini AI
        """
        self.headless = headless
        self.timeout = timeout
        self.status_callback = status_callback
        self.max_retries = max_retries
        self.cancel_check = cancel_check
        self.captcha_mode = captcha_mode
        self.gemini_settings = gemini_settings or {}
        self._cancelled = False
        self.browser = None
    
    def update_status(self, message: str, progress: int = 0):
        """Update status via callback"""
        logger.info(f"[StealthChecker] {message}")
        if self.status_callback:
            self.status_callback(message, progress)
    
    def is_cancelled(self) -> bool:
        """Check if task has been cancelled"""
        if self._cancelled:
            return True
        if self.cancel_check and self.cancel_check():
            self._cancelled = True
            self.update_status("Task cancelled by user", 0)
            return True
        return False
    
    def force_cancel(self):
        """Force cancel the task"""
        self._cancelled = True
        if self.browser:
            try:
                self.browser.close()
            except:
                pass
    
    def check_balance(self, card_number: str, exp_month: str, exp_year: str, cvv: str) -> dict:
        """
        Check card balance using stealth browser.
        
        این تابع sync هست (برخلاف CardChecker که async هست)
        
        Args:
            card_number: شماره کارت 16 رقمی
            exp_month: ماه انقضا
            exp_year: سال انقضا (2 رقم)
            cvv: کد CVV
            
        Returns:
            Dictionary containing result
        """
        try:
            if self.is_cancelled():
                return {'success': False, 'error': 'Task cancelled', 'cancelled': True}
            
            # Start stealth browser
            self.update_status("🔒 Starting Stealth Browser (UC Mode)...", 10)
            self.browser = StealthBrowser(
                headless=self.headless,
                timeout=self.timeout,
                status_callback=self.status_callback
            )
            
            if not self.browser.start():
                return {'success': False, 'error': 'Failed to start stealth browser'}
            
            if self.is_cancelled():
                self.browser.close()
                return {'success': False, 'error': 'Task cancelled', 'cancelled': True}
            
            # Navigate to site
            self.update_status(f"🌐 Opening {self.SITE_URL}...", 20)
            if not self.browser.navigate(self.SITE_URL, wait_time=5):
                self.browser.close()
                return {'success': False, 'error': 'Failed to load website'}
            
            self.update_status("✅ Website loaded successfully", 25)
            time.sleep(1)
            
            if self.is_cancelled():
                self.browser.close()
                return {'success': False, 'error': 'Task cancelled', 'cancelled': True}
            
            # Check if browser is still alive
            if not self.browser.is_alive():
                return {'success': False, 'error': 'Browser closed unexpectedly before filling form'}
            
            # Fill the form
            self.update_status("📝 Filling card information...", 30)
            success = self._fill_card_form(card_number, exp_month, exp_year, cvv)
            
            if not success:
                if self.browser.is_alive():
                    self.browser.close()
                return {'success': False, 'error': 'Failed to fill card form'}
            
            self.update_status("✅ Form filled successfully", 50)
            
            if self.is_cancelled():
                if self.browser.is_alive():
                    self.browser.close()
                return {'success': False, 'error': 'Task cancelled', 'cancelled': True}
            
            # Check if browser is still alive
            if not self.browser.is_alive():
                return {'success': False, 'error': 'Browser closed unexpectedly after filling form'}
            
            # Handle CAPTCHA
            self.update_status("🔐 Handling CAPTCHA...", 55)
            captcha_solved = self._handle_captcha()
            
            if not captcha_solved:
                # Take screenshot for debugging
                self.browser.take_screenshot("captcha_failed.png")
                self.browser.close()
                return {'success': False, 'error': 'CAPTCHA not solved'}
            
            self.update_status("✅ CAPTCHA solved!", 70)
            
            if self.is_cancelled():
                self.browser.close()
                return {'success': False, 'error': 'Task cancelled', 'cancelled': True}
            
            # Submit form
            self.update_status("🚀 Submitting form...", 75)
            if not self._submit_form():
                self.browser.close()
                return {'success': False, 'error': 'Failed to submit form'}
            
            # Wait for result
            self.update_status("⏳ Waiting for result...", 80)
            time.sleep(3)
            
            # Extract balance
            result = self._extract_balance()
            
            # Take screenshot
            self.browser.take_screenshot(f"result_{card_number[-4:]}.png")
            
            # Close browser
            self.browser.close()
            
            return result
            
        except Exception as e:
            logger.error(f"Error in stealth check: {e}")
            if self.browser:
                try:
                    self.browser.take_screenshot("error.png")
                    self.browser.close()
                except:
                    pass
            return {'success': False, 'error': str(e)}
    
    def _fill_card_form(self, card_number: str, exp_month: str, exp_year: str, cvv: str) -> bool:
        """Fill the card form fields"""
        try:
            # Wait for form to be ready
            time.sleep(1)
            
            # Card number field
            card_filled = False
            try:
                if self.browser.type_text('input[name="cardNumber"], #cardNumber, input[placeholder*="card"]', 
                                          card_number, clear=True):
                    card_filled = True
            except Exception as e:
                logger.debug(f"Primary card selector failed: {e}")
            
            if not card_filled:
                # Try alternate selectors
                try:
                    card_inputs = self.browser.find_elements('input[type="text"], input[type="tel"]')
                    if card_inputs and len(card_inputs) > 0:
                        try:
                            card_inputs[0].clear()
                        except Exception:
                            pass
                        card_inputs[0].send_keys(card_number)
                        card_filled = True
                except Exception as e:
                    logger.debug(f"Alternate card selector failed: {e}")
            
            if not card_filled:
                logger.warning("Could not fill card number field")
            
            time.sleep(0.3)
            
            # Expiration month
            try:
                self.browser.type_text('input[name="expMonth"], #expMonth, input[placeholder*="MM"]', 
                                       exp_month, clear=True)
            except Exception as e:
                logger.debug(f"Exp month failed: {e}")
            
            time.sleep(0.2)
            
            # Expiration year
            try:
                self.browser.type_text('input[name="expYear"], #expYear, input[placeholder*="YY"]', 
                                       exp_year, clear=True)
            except Exception as e:
                logger.debug(f"Exp year failed: {e}")
            
            time.sleep(0.2)
            
            # CVV
            try:
                self.browser.type_text('input[name="cvv"], #cvv, input[placeholder*="CVV"]', 
                                       cvv, clear=True)
            except Exception as e:
                logger.debug(f"CVV failed: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error filling form: {e}")
            return False
    
    def _handle_captcha(self) -> bool:
        """Handle reCAPTCHA"""
        try:
            self.update_status("🔐 Looking for CAPTCHA...", 60)
            
            captcha_clicked = False
            
            # روش 1: متد اصلی handle_captcha_checkbox
            self.update_status("🔐 Trying method 1: handle_captcha_checkbox...", 61)
            try:
                if self.browser.handle_captcha_checkbox():
                    self.update_status("✅ CAPTCHA checkbox clicked (method 1)", 62)
                    captcha_clicked = True
                    time.sleep(2)
            except Exception as e:
                logger.debug(f"Method 1 failed: {e}")
            
            # چک کردن موفقیت
            if captcha_clicked:
                try:
                    page_source = self.browser.get_page_source()
                    if page_source and ('recaptcha-checkbox-checked' in page_source or 'recaptcha-checkbox-checkmark' in page_source):
                        self.update_status("✅ CAPTCHA solved!", 65)
                        return True
                except:
                    pass
            
            # روش 2: متد click_recaptcha_v2
            if not captcha_clicked:
                self.update_status("🔐 Trying method 2: click_recaptcha_v2...", 62)
                try:
                    if self.browser.click_recaptcha_v2():
                        self.update_status("✅ CAPTCHA checkbox clicked (method 2)", 63)
                        captcha_clicked = True
                        time.sleep(2)
                except Exception as e:
                    logger.debug(f"Method 2 failed: {e}")
            
            # چک کردن موفقیت دوباره
            if captcha_clicked:
                try:
                    page_source = self.browser.get_page_source()
                    if page_source and ('recaptcha-checkbox-checked' in page_source or 'recaptcha-checkbox-checkmark' in page_source):
                        self.update_status("✅ CAPTCHA solved!", 65)
                        return True
                except:
                    pass
            
            # روش 3: handle_captcha کامل
            self.update_status("🔐 Trying method 3: full captcha handler...", 63)
            try:
                if self.browser.handle_captcha():
                    self.update_status("✅ Full CAPTCHA handler succeeded", 65)
                    time.sleep(2)
                    return True
            except Exception as e:
                logger.debug(f"Method 3 failed: {e}")
            
            # Manual wait mode - اگر هیچکدوم نگرفت
            if self.captcha_mode == 'manual' or not captcha_clicked:
                wait_time = 60 if self.captcha_mode == 'manual' else 30
                self.update_status(f"⏳ Waiting for CAPTCHA ({wait_time}s)... Please solve it manually if needed", 65)
                
                for i in range(wait_time):
                    if self.is_cancelled():
                        return False
                    
                    try:
                        page_source = self.browser.get_page_source()
                        if page_source and ('recaptcha-checkbox-checked' in page_source or 'recaptcha-checkbox-checkmark' in page_source):
                            self.update_status("✅ CAPTCHA solved!", 70)
                            return True
                    except Exception:
                        pass
                    
                    time.sleep(1)
                    if i % 10 == 0 and i > 0:
                        self.update_status(f"⏳ Still waiting... ({wait_time-i}s remaining)", 65)
                
                # اگر تا اینجا رسیدیم یعنی timeout شد
                if not captcha_clicked:
                    return False
            
            # Auto mode - فرض میکنیم کار کرده
            return captcha_clicked
            
        except Exception as e:
            logger.error(f"Error handling CAPTCHA: {e}")
            return False
    
    def _submit_form(self) -> bool:
        """Submit the form"""
        try:
            # Look for submit button
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:contains("Check")',
                'button:contains("Submit")',
                '.submit-btn',
                '#submit'
            ]
            
            for selector in submit_selectors:
                try:
                    if self.browser.click(selector):
                        time.sleep(2)
                        return True
                except Exception as e:
                    logger.debug(f"Submit selector {selector} failed: {e}")
                    continue
            
            # Try clicking any button that looks like submit
            try:
                buttons = self.browser.find_elements('button')
                for btn in buttons:
                    try:
                        text = btn.text.lower() if btn.text else ""
                        if 'check' in text or 'submit' in text or 'balance' in text:
                            if self.browser.driver:
                                self.browser.driver.uc_click(btn)
                                time.sleep(2)
                                return True
                    except Exception as e:
                        logger.debug(f"Button click failed: {e}")
                        continue
            except Exception as e:
                logger.debug(f"Button search failed: {e}")
            
            return False
            
        except Exception as e:
            logger.error(f"Error submitting form: {e}")
            return False
    
    def _extract_balance(self) -> dict:
        """Extract balance from result page"""
        try:
            page_source = self.browser.get_page_source()
            
            # Look for balance patterns
            import re
            
            # Pattern 1: $XX.XX format
            balance_patterns = [
                r'\$\d+(?:,\d{3})*(?:\.\d{2})?',  # $1,234.56 or $123.45
                r'balance[:\s]*\$?(\d+(?:\.\d{2})?)',  # balance: 123.45
                r'(\d+(?:\.\d{2})?)\s*(?:USD|dollars?)',  # 123.45 USD
            ]
            
            for pattern in balance_patterns:
                matches = re.findall(pattern, page_source, re.IGNORECASE)
                if matches:
                    balance = matches[0] if isinstance(matches[0], str) else matches[0][0]
                    if not balance.startswith('$'):
                        balance = f"${balance}"
                    
                    self.update_status(f"💰 Balance found: {balance}", 90)
                    return {
                        'success': True,
                        'balance': balance,
                        'message': 'Balance retrieved successfully',
                        'check_date': datetime.now().isoformat()
                    }
            
            # Check for error messages
            error_patterns = [
                r'invalid card',
                r'card not found',
                r'error',
                r'failed',
                r'incorrect'
            ]
            
            for pattern in error_patterns:
                if re.search(pattern, page_source, re.IGNORECASE):
                    return {
                        'success': False,
                        'error': 'Card validation failed',
                        'balance': None
                    }
            
            # No balance found
            return {
                'success': False,
                'error': 'Could not find balance on page',
                'balance': None
            }
            
        except Exception as e:
            logger.error(f"Error extracting balance: {e}")
            return {'success': False, 'error': str(e), 'balance': None}


# Async wrapper for compatibility with existing code
async def check_balance_stealth(
    card_number: str, 
    exp_month: str, 
    exp_year: str, 
    cvv: str,
    headless: bool = False,
    status_callback: Callable = None,
    cancel_check: Callable = None,
    **kwargs
) -> dict:
    """
    Async wrapper for StealthCardChecker.
    
    این تابع async هست برای سازگاری با app.py
    """
    import asyncio
    
    checker = StealthCardChecker(
        headless=headless,
        status_callback=status_callback,
        cancel_check=cancel_check,
        **kwargs
    )
    
    # Run sync code in thread pool
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        checker.check_balance,
        card_number, exp_month, exp_year, cvv
    )
    
    return result


if __name__ == "__main__":
    # تست ساده
    print("=" * 50)
    print("🔒 Stealth Card Checker Test")
    print("=" * 50)
    
    checker = StealthCardChecker(
        headless=False,
        status_callback=lambda msg, prog: print(f"[{prog}%] {msg}")
    )
    
    # تست با داده‌های فیک
    result = checker.check_balance(
        card_number="4111111111111111",
        exp_month="12",
        exp_year="25",
        cvv="123"
    )
    
    print(f"\nResult: {result}")
