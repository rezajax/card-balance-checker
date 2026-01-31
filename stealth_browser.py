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
        from seleniumbase import Driver
        
        self.update_status("🔒 Starting Stealth Browser (UC Mode)...", 10)
        
        try:
            # استفاده از Driver mode برای کنترل بیشتر
            self.driver = Driver(
                uc=True,
                headless=self.headless,
                proxy=self.proxy
            )
            self._is_open = True
            self.update_status("✅ Stealth Browser started successfully", 15)
            return True
        except Exception as e:
            logger.error(f"Failed to start stealth browser: {e}")
            self.update_status(f"❌ Failed to start browser: {e}", 0)
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
        
        try:
            if by == "xpath":
                return self.driver.find_element("xpath", selector)
            return self.driver.find_element("css selector", selector)
        except Exception as e:
            logger.debug(f"Element not found: {selector} - {e}")
            return None
    
    def find_elements(self, selector: str, by: str = "css"):
        """پیدا کردن چند element"""
        if not self.driver:
            return []
        
        try:
            if by == "xpath":
                return self.driver.find_elements("xpath", selector)
            return self.driver.find_elements("css selector", selector)
        except Exception as e:
            logger.debug(f"Elements not found: {selector} - {e}")
            return []
    
    def click(self, selector: str, by: str = "css"):
        """
        کلیک stealth روی element
        """
        try:
            element = self.find_element(selector, by)
            if element:
                self.driver.uc_click(element)
                return True
            return False
        except Exception as e:
            logger.warning(f"Click failed: {selector} - {e}")
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
        try:
            element = self.find_element(selector, by)
            if element:
                if clear:
                    try:
                        element.clear()
                    except Exception:
                        pass  # بعضی فیلدها clear نمیشن
                element.send_keys(text)
                return True
            return False
        except Exception as e:
            logger.warning(f"Type text failed: {selector} - {e}")
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
        چند روش مختلف امتحان میشه
        """
        # روش 1: استفاده از uc_gui_click_captcha
        try:
            logger.info("Trying uc_gui_click_captcha...")
            self.driver.uc_gui_click_captcha()
            time.sleep(1)
            return True
        except Exception as e:
            logger.debug(f"uc_gui_click_captcha failed: {e}")
        
        # روش 2: سوییچ به iframe و کلیک مستقیم
        try:
            logger.info("Trying iframe switch method...")
            # پیدا کردن iframe های reCAPTCHA
            iframes = self.driver.find_elements("css selector", "iframe[src*='recaptcha'], iframe[title*='reCAPTCHA']")
            for iframe in iframes:
                try:
                    self.driver.switch_to.frame(iframe)
                    # پیدا کردن checkbox
                    checkbox = self.driver.find_element("css selector", ".recaptcha-checkbox, #recaptcha-anchor, .rc-anchor-checkbox")
                    if checkbox:
                        self.driver.uc_click(checkbox)
                        time.sleep(1)
                        self.driver.switch_to.default_content()
                        return True
                except Exception:
                    self.driver.switch_to.default_content()
                    continue
        except Exception as e:
            logger.debug(f"iframe method failed: {e}")
            try:
                self.driver.switch_to.default_content()
            except:
                pass
        
        # روش 3: کلیک با JavaScript
        try:
            logger.info("Trying JavaScript click...")
            script = """
            var frames = document.querySelectorAll('iframe[src*="recaptcha"]');
            for(var i = 0; i < frames.length; i++) {
                try {
                    var checkbox = frames[i].contentWindow.document.querySelector('.recaptcha-checkbox');
                    if(checkbox) { checkbox.click(); return true; }
                } catch(e) {}
            }
            return false;
            """
            result = self.driver.execute_script(script)
            if result:
                time.sleep(1)
                return True
        except Exception as e:
            logger.debug(f"JavaScript click failed: {e}")
        
        # روش 4: کلیک روی container
        try:
            logger.info("Trying container click...")
            containers = self.driver.find_elements("css selector", ".g-recaptcha, [data-sitekey], .recaptcha-checkbox-border")
            for container in containers:
                try:
                    self.driver.uc_click(container)
                    time.sleep(1)
                    return True
                except:
                    continue
        except Exception as e:
            logger.debug(f"Container click failed: {e}")
        
        return False
    
    def handle_captcha(self):
        """
        Handle کردن CAPTCHA پیچیده‌تر
        """
        try:
            logger.info("Trying uc_gui_handle_captcha...")
            self.driver.uc_gui_handle_captcha()
            return True
        except Exception as e:
            logger.warning(f"Could not handle captcha: {e}")
            return False
    
    def click_recaptcha_v2(self):
        """
        روش خاص برای کلیک روی reCAPTCHA v2 checkbox
        """
        try:
            # صبر برای لود شدن CAPTCHA
            time.sleep(2)
            
            # پیدا کردن iframe اصلی
            iframe_selectors = [
                "iframe[src*='google.com/recaptcha']",
                "iframe[src*='recaptcha/api2/anchor']",
                "iframe[title*='reCAPTCHA']",
            ]
            
            for selector in iframe_selectors:
                try:
                    iframes = self.driver.find_elements("css selector", selector)
                    if iframes:
                        iframe = iframes[0]
                        # استفاده از uc_switch_to_frame
                        try:
                            self.driver.uc_switch_to_frame(iframe)
                        except:
                            self.driver.switch_to.frame(iframe)
                        
                        # کلیک روی checkbox
                        checkbox_selectors = [
                            "#recaptcha-anchor",
                            ".recaptcha-checkbox-border",
                            ".recaptcha-checkbox",
                            "span[role='checkbox']"
                        ]
                        
                        for cb_selector in checkbox_selectors:
                            try:
                                checkbox = self.driver.find_element("css selector", cb_selector)
                                if checkbox:
                                    self.driver.uc_click(checkbox)
                                    time.sleep(2)
                                    self.driver.switch_to.default_content()
                                    return True
                            except:
                                continue
                        
                        self.driver.switch_to.default_content()
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    try:
                        self.driver.switch_to.default_content()
                    except:
                        pass
            
            return False
        except Exception as e:
            logger.error(f"click_recaptcha_v2 failed: {e}")
            try:
                self.driver.switch_to.default_content()
            except:
                pass
            return False
    
    def execute_script(self, script: str):
        """اجرای JavaScript"""
        if self.driver:
            return self.driver.execute_script(script)
        return None
    
    def sleep(self, seconds: float):
        """صبر کردن"""
        time.sleep(seconds)
    
    def is_alive(self) -> bool:
        """چک کردن اینکه مرورگر هنوز باز هست"""
        if not self.driver or not self._is_open:
            return False
        try:
            # سعی میکنیم URL فعلی رو بگیریم - اگر مرورگر بسته باشه خطا میده
            _ = self.driver.current_url
            return True
        except Exception:
            self._is_open = False
            return False
    
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
