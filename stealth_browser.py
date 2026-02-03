"""
Stealth Browser Automation - Bypass Cloudflare & Anti-Bot Detection

این ماژول برای دور زدن سیستم‌های ضد ربات مثل Cloudflare، DataDome و غیره طراحی شده.
از SeleniumBase UC Mode استفاده می‌کنه که بهترین روش برای bypass کردن anti-bot هست.

نصب:
    pip install seleniumbase undetected-chromedriver
"""

import time
import logging
from typing import Optional, Callable, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================
# StealthBrowser - کلاس اصلی برای استفاده در پروژه
# ============================================

class StealthBrowser:
    """
    Wrapper class for SeleniumBase UC Mode.
    این کلاس interface مشابه Playwright داره برای یکپارچگی با بقیه پروژه.
    
    مزایا:
    - خودکار DevTools variables رو rename می‌کنه
    - موقع page load خودش disconnect میشه
    - متدهای خاص برای handle کردن CAPTCHA داره
    - تشخیص نمیده که automation داره اجرا میشه
    """
    
    def __init__(
        self, 
        headless: bool = False, 
        timeout: int = 60000,
        status_callback: Callable = None,
        proxy: str = None
    ):
        """
        Args:
            headless: اجرا بدون نمایش مرورگر
            timeout: حداکثر زمان انتظار (میلی‌ثانیه)
            status_callback: تابع callback برای آپدیت وضعیت
            proxy: آدرس پروکسی (اختیاری)
        """
        self.headless = headless
        self.timeout = timeout // 1000  # تبدیل به ثانیه
        self.status_callback = status_callback
        self.proxy = proxy
        self.sb = None
        self.driver = None
        self._is_open = False
    
    def update_status(self, message: str, progress: int = 0):
        """Update status via callback"""
        logger.info(f"[StealthBrowser] {message}")
        if self.status_callback:
            self.status_callback(message, progress)
    
    def start(self):
        """شروع مرورگر stealth"""
        import subprocess
        import tempfile
        import shutil
        from seleniumbase import Driver
        
        self.update_status("🔒 Starting Stealth Browser (UC Mode)...", 10)
        
        # Clean up zombie chromedriver processes first
        try:
            subprocess.run(['pkill', '-9', '-f', 'chromedriver'], capture_output=True, timeout=3)
            time.sleep(0.5)
        except:
            pass
        
        # Create a fresh temp user data directory
        self._temp_user_data = tempfile.mkdtemp(prefix='stealth_browser_')
        logger.info(f"Using temp user data dir: {self._temp_user_data}")
        
        try:
            # استفاده از Driver mode برای کنترل بیشتر
            self.driver = Driver(
                uc=True,
                headless=self.headless,
                proxy=self.proxy,
                user_data_dir=self._temp_user_data
            )
            self._is_open = True
            self.update_status("✅ Stealth Browser started successfully", 15)
            return True
        except Exception as e:
            logger.error(f"Failed to start stealth browser: {e}")
            self.update_status(f"❌ Failed to start browser: {e}", 0)
            # Cleanup temp dir on failure
            try:
                shutil.rmtree(self._temp_user_data, ignore_errors=True)
            except:
                pass
            return False
    
    def navigate(self, url: str, wait_time: int = 4):
        """
        Navigate to URL with stealth reconnect
        
        Args:
            url: آدرس سایت
            wait_time: زمان انتظار برای Cloudflare challenge (ثانیه)
        """
        if not self._is_open:
            raise RuntimeError("Browser not started. Call start() first.")
        
        self.update_status(f"🌐 Navigating to {url}...", 20)
        
        try:
            # استفاده از uc_open_with_reconnect برای bypass کردن Cloudflare
            self.driver.uc_open_with_reconnect(url, wait_time)
            self.update_status(f"✅ Page loaded: {self.driver.title}", 25)
            return True
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            self.update_status(f"❌ Navigation failed: {e}", 0)
            return False
    
    def get_page_source(self) -> str:
        """گرفتن HTML صفحه"""
        if self.driver:
            return self.driver.page_source
        return ""
    
    def get_title(self) -> str:
        """گرفتن عنوان صفحه"""
        if self.driver:
            return self.driver.title
        return ""
    
    def get_current_url(self) -> str:
        """گرفتن URL فعلی"""
        if self.driver:
            return self.driver.current_url
        return ""
    
    def find_element(self, selector: str, by: str = "css"):
        """
        پیدا کردن element
        
        Args:
            selector: سلکتور CSS یا XPath
            by: نوع سلکتور ('css' یا 'xpath')
        """
        if not self.driver:
            return None
        
        if by == "xpath":
            return self.driver.find_element("xpath", selector)
        return self.driver.find_element("css selector", selector)
    
    def find_elements(self, selector: str, by: str = "css"):
        """پیدا کردن چند element"""
        if not self.driver:
            return []
        
        if by == "xpath":
            return self.driver.find_elements("xpath", selector)
        return self.driver.find_elements("css selector", selector)
    
    def click(self, selector: str, by: str = "css"):
        """
        کلیک stealth روی element
        """
        element = self.find_element(selector, by)
        if element:
            self.driver.uc_click(element)
            return True
        return False
    
    def type_text(self, selector: str, text: str, by: str = "css", clear: bool = True):
        """
        تایپ کردن در input field
        
        Args:
            selector: سلکتور element
            text: متن برای تایپ
            by: نوع سلکتور
            clear: پاک کردن فیلد قبل از تایپ
        """
        element = self.find_element(selector, by)
        if element:
            if clear:
                element.clear()
            element.send_keys(text)
            return True
        return False
    
    def wait_for_element(self, selector: str, timeout: int = None, by: str = "css"):
        """
        صبر کردن تا element ظاهر شود
        """
        if timeout is None:
            timeout = self.timeout
        
        try:
            if by == "xpath":
                self.driver.wait_for_element(selector, by="xpath", timeout=timeout)
            else:
                self.driver.wait_for_element(selector, timeout=timeout)
            return True
        except:
            return False
    
    def take_screenshot(self, filename: str = None) -> str:
        """گرفتن اسکرین‌شات"""
        if filename is None:
            filename = f"stealth_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        if self.driver:
            self.driver.save_screenshot(filename)
            return filename
        return None
    
    def handle_captcha_checkbox(self):
        """
        کلیک روی checkbox CAPTCHA (اگر وجود داشته باشد)
        """
        try:
            self.driver.uc_gui_click_captcha()
            return True
        except Exception as e:
            logger.warning(f"Could not click captcha checkbox: {e}")
            return False
    
    def handle_captcha(self):
        """
        Handle کردن CAPTCHA پیچیده‌تر
        """
        try:
            self.driver.uc_gui_handle_captcha()
            return True
        except Exception as e:
            logger.warning(f"Could not handle captcha: {e}")
            return False
    
    def execute_script(self, script: str):
        """اجرای JavaScript"""
        if self.driver:
            return self.driver.execute_script(script)
        return None
    
    def sleep(self, seconds: float):
        """صبر کردن"""
        time.sleep(seconds)
    
    def close(self):
        """بستن مرورگر"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
        self._is_open = False
        self.update_status("🔒 Stealth Browser closed", 100)
    
    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


# ============================================
# توابع کمکی
# ============================================

def test_bot_detection(headless: bool = False):
    """
    تست کن ببین مرورگرت قابل تشخیصه یا نه
    """
    from seleniumbase import SB
    
    test_urls = [
        "https://bot.sannysoft.com/",           # تست جامع fingerprint
        "https://bot-detector.rebrowser.net/", # تست CDP detection
        "https://nowsecure.nl/",                # تست Cloudflare
    ]
    
    results = []
    
    with SB(uc=True, headless=headless) as sb:
        for url in test_urls:
            print(f"\n🔍 Testing: {url}")
            try:
                sb.uc_open_with_reconnect(url, 4)
                title = sb.get_title()
                print(f"   ✅ Title: {title}")
                results.append({'url': url, 'success': True, 'title': title})
            except Exception as e:
                print(f"   ❌ Failed: {e}")
                results.append({'url': url, 'success': False, 'error': str(e)})
            time.sleep(2)
    
    return results


def quick_stealth_test(url: str, headless: bool = False) -> dict:
    """
    تست سریع یک URL با مرورگر stealth
    """
    with StealthBrowser(headless=headless) as browser:
        if browser.navigate(url):
            return {
                'success': True,
                'title': browser.get_title(),
                'url': browser.get_current_url()
            }
        return {'success': False, 'error': 'Navigation failed'}


# ============================================
# اجرای مستقیم
# ============================================

if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Stealth Browser Test")
    print("=" * 50)
    
    test_url = input("Enter URL to test (or press Enter for default): ").strip()
    if not test_url:
        test_url = "https://bot.sannysoft.com/"
    
    print(f"\n🚀 Testing with Stealth Browser...")
    result = quick_stealth_test(test_url)
    print(f"\nResult: {result}")
