#!/usr/bin/env python3
"""
Browser Automation Script - نسخه پیشرفته
با قابلیت‌های اضافی: retry, logging, error handling
"""

import asyncio
from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
from typing import List, Dict, Optional
import json
from datetime import datetime
import logging
from pathlib import Path
import os
from dotenv import load_dotenv


# تنظیم logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('automation.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AdvancedBrowserAutomation:
    """کلاس پیشرفته برای اتومیشن مرورگر با قابلیت‌های حرفه‌ای"""
    
    def __init__(self, headless: bool = False, slow_mo: int = 0):
        """
        Args:
            headless: اگر True باشه، مرورگر نمایش داده نمیشه
            slow_mo: تاخیر بین عملیات به میلی‌ثانیه (برای debug)
        """
        self.headless = headless
        self.slow_mo = slow_mo
        self.browser: Browser = None
        self.page: Page = None
        self.playwright = None
        
    async def initialize(self, browser_type: str = 'chromium'):
        """
        راه‌اندازی مرورگر
        
        Args:
            browser_type: نوع مرورگر (chromium, firefox, webkit)
        """
        logger.info(f"راه‌اندازی مرورگر {browser_type}...")
        
        self.playwright = await async_playwright().start()
        
        # انتخاب نوع مرورگر
        if browser_type == 'firefox':
            browser_launcher = self.playwright.firefox
        elif browser_type == 'webkit':
            browser_launcher = self.playwright.webkit
        else:
            browser_launcher = self.playwright.chromium
            
        self.browser = await browser_launcher.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-web-security',  # برای CORS
            ]
        )
        
        # ساخت context با قابلیت‌های پیشرفته
        context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='fa-IR',
            timezone_id='Asia/Tehran',
            permissions=['geolocation'],  # اگر نیاز به location هست
            # record_video_dir='videos',  # ضبط ویدیو از اجرا
        )
        
        # اضافه کردن script برای پنهان کردن automation
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        self.page = await context.new_page()
        self.page.set_default_timeout(30000)
        
        # Handle console messages
        self.page.on('console', lambda msg: logger.debug(f"Browser console: {msg.text}"))
        
        # Handle page errors
        self.page.on('pageerror', lambda err: logger.error(f"Page error: {err}"))
        
        logger.info("✅ مرورگر آماده است")
        
    async def navigate_with_retry(self, url: str, max_retries: int = 3):
        """
        باز کردن وبسایت با قابلیت retry
        
        Args:
            url: آدرس وبسایت
            max_retries: تعداد دفعات تلاش مجدد
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"تلاش {attempt + 1}/{max_retries} برای باز کردن {url}")
                
                response = await self.page.goto(url, wait_until='domcontentloaded')
                
                if response and response.ok:
                    await self.page.wait_for_load_state('networkidle', timeout=10000)
                    logger.info("✅ وبسایت با موفقیت باز شد")
                    return True
                else:
                    logger.warning(f"پاسخ نامعتبر: {response.status if response else 'No response'}")
                    
            except PlaywrightTimeout:
                logger.warning(f"Timeout در تلاش {attempt + 1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    
            except Exception as e:
                logger.error(f"خطا در باز کردن صفحه: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    
        raise Exception(f"ناموفق در باز کردن {url} بعد از {max_retries} تلاش")
        
    async def smart_fill(self, selector: str, value: str, method: str = 'type'):
        """
        وارد کردن داده به روش هوشمند
        
        Args:
            selector: سلکتور المنت
            value: مقدار برای وارد کردن
            method: روش وارد کردن (type, fill, press)
        """
        # چند روش مختلف برای پیدا کردن المنت
        selectors_to_try = [
            selector,  # سلکتور اصلی
            f"xpath={selector}" if not selector.startswith('xpath=') else selector,
            f"text={selector}",  # اگر متن باشه
        ]
        
        for sel in selectors_to_try:
            try:
                await self.page.wait_for_selector(sel, state='visible', timeout=5000)
                
                if method == 'type':
                    await self.page.fill(sel, '')  # پاک کردن
                    await self.page.type(sel, value, delay=50)
                elif method == 'fill':
                    await self.page.fill(sel, value)
                elif method == 'press':
                    element = await self.page.query_selector(sel)
                    await element.press_sequentially(value)
                    
                logger.info(f"✓ مقدار '{value}' وارد شد")
                return True
                
            except Exception as e:
                continue
                
        raise Exception(f"نمی‌توان المنت {selector} را پیدا کرد")
        
    async def smart_click(self, selector: str, wait_for_navigation: bool = False):
        """
        کلیک هوشمند با انتظار برای load شدن
        
        Args:
            selector: سلکتور المنت
            wait_for_navigation: منتظر navigation بمونه؟
        """
        await self.page.wait_for_selector(selector, state='visible')
        
        # Scroll به المنت
        await self.page.locator(selector).scroll_into_view_if_needed()
        
        # کلیک
        if wait_for_navigation:
            async with self.page.expect_navigation():
                await self.page.click(selector)
        else:
            await self.page.click(selector)
            
        logger.info(f"✓ کلیک روی {selector}")
        
    async def extract_data(self, selectors: Dict[str, str]) -> Dict[str, str]:
        """
        استخراج داده‌ها به صورت دیکشنری
        
        Args:
            selectors: دیکشنری از {name: selector}
            
        Returns:
            دیکشنری از {name: value}
        """
        results = {}
        
        for name, selector in selectors.items():
            try:
                await self.page.wait_for_selector(selector, state='visible', timeout=10000)
                element = await self.page.query_selector(selector)
                
                # سعی در گرفتن محتوا به روش‌های مختلف
                text = await element.inner_text()
                if not text:
                    text = await element.text_content()
                if not text:
                    text = await element.get_attribute('value')
                    
                results[name] = text.strip() if text else None
                logger.info(f"✓ {name}: {results[name]}")
                
            except Exception as e:
                logger.error(f"✗ خطا در خواندن {name}: {e}")
                results[name] = None
                
        return results
        
    async def wait_for_element(self, selector: str, timeout: int = 30000, state: str = 'visible'):
        """
        انتظار برای ظاهر شدن المنت
        
        Args:
            selector: سلکتور المنت
            timeout: حداکثر زمان انتظار (میلی‌ثانیه)
            state: حالت مورد انتظار (visible, hidden, attached, detached)
        """
        try:
            await self.page.wait_for_selector(selector, timeout=timeout, state=state)
            return True
        except PlaywrightTimeout:
            logger.warning(f"Timeout: المنت {selector} پیدا نشد")
            return False
            
    async def save_results(self, data: Dict, filename: str = None):
        """ذخیره نتایج در فایل JSON"""
        if filename is None:
            filename = f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
        output = {
            'timestamp': datetime.now().isoformat(),
            'data': data
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
            
        logger.info(f"💾 نتایج در {filename} ذخیره شد")
        
    async def close(self):
        """بستن مرورگر"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("🔒 مرورگر بسته شد")


async def main():
    """تابع اصلی - نسخه پیشرفته"""
    
    # بارگذاری متغیرهای محیطی
    load_dotenv()
    
    # تنظیمات از environment variables یا مقادیر پیش‌فرض
    CONFIG = {
        'url': os.getenv('WEBSITE_URL', 'https://example.com'),
        'input_numbers': os.getenv('INPUT_NUMBERS', '123,456,789').split(','),
        'input_selectors': os.getenv('INPUT_SELECTORS', '#input1,#input2,#input3').split(','),
        'submit_selector': os.getenv('SUBMIT_SELECTOR', 'button[type="submit"]'),
        'result_selectors': {
            'result_1': os.getenv('RESULT_SELECTOR_1', '.result-1'),
            'result_2': os.getenv('RESULT_SELECTOR_2', '.result-2'),
        },
        'headless': os.getenv('HEADLESS', 'false').lower() == 'true',
        'browser_type': os.getenv('BROWSER_TYPE', 'chromium'),  # chromium, firefox, webkit
    }
    
    automation = AdvancedBrowserAutomation(
        headless=CONFIG['headless'],
        slow_mo=50  # تاخیر 50ms بین عملیات
    )
    
    try:
        logger.info("=" * 60)
        logger.info("🤖 شروع اتومیشن پیشرفته مرورگر")
        logger.info("=" * 60)
        
        # راه‌اندازی
        await automation.initialize(browser_type=CONFIG['browser_type'])
        
        # باز کردن وبسایت با retry
        await automation.navigate_with_retry(CONFIG['url'])
        
        # وارد کردن اعداد
        logger.info("📝 وارد کردن اعداد...")
        for number, selector in zip(CONFIG['input_numbers'], CONFIG['input_selectors']):
            await automation.smart_fill(selector, number.strip())
            await asyncio.sleep(0.3)  # تاخیر طبیعی
            
        # سابمیت فرم
        logger.info("🚀 ارسال فرم...")
        await automation.smart_click(CONFIG['submit_selector'], wait_for_navigation=True)
        
        # خواندن نتایج
        logger.info("📊 استخراج نتایج...")
        results = await automation.extract_data(CONFIG['result_selectors'])
        
        # نمایش و ذخیره نتایج
        logger.info("\n" + "=" * 60)
        logger.info("📋 نتایج نهایی:")
        logger.info("=" * 60)
        for key, value in results.items():
            logger.info(f"  {key}: {value}")
            
        # ذخیره نتایج
        await automation.save_results({
            'inputs': CONFIG['input_numbers'],
            'results': results
        })
        
        # اسکرین‌شات
        await automation.page.screenshot(
            path=f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
            full_page=True
        )
        
        logger.info("\n✅ اتومیشن با موفقیت تمام شد!")
        
    except Exception as e:
        logger.error(f"\n❌ خطا: {e}", exc_info=True)
        try:
            await automation.page.screenshot(path='error_screenshot.png')
        except:
            pass
            
    finally:
        await automation.close()


if __name__ == '__main__':
    asyncio.run(main())
