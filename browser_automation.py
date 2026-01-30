#!/usr/bin/env python3
"""
Browser Automation Script with Playwright
استفاده از بهترین تکنولوژی‌های اتومیشن
"""

import asyncio
from playwright.async_api import async_playwright, Page, Browser
from typing import List, Dict
import json
from datetime import datetime


class BrowserAutomation:
    """کلاس اصلی برای اتومیشن مرورگر"""
    
    def __init__(self, headless: bool = False):
        """
        Args:
            headless: اگر True باشه، مرورگر نمایش داده نمیشه
        """
        self.headless = headless
        self.browser: Browser = None
        self.page: Page = None
        
    async def initialize(self):
        """راه‌اندازی مرورگر"""
        playwright = await async_playwright().start()
        # از Chromium استفاده میکنیم (سریعترین و پایدارترین)
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',  # پنهان کردن automation
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        )
        
        # ساخت context با تنظیمات واقعی‌تر
        context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='fa-IR',  # زبان فارسی
            timezone_id='Asia/Tehran'
        )
        
        self.page = await context.new_page()
        
        # تنظیمات timeout
        self.page.set_default_timeout(30000)  # 30 ثانیه
        
    async def navigate_to_website(self, url: str):
        """
        باز کردن وبسایت
        
        Args:
            url: آدرس وبسایت
        """
        print(f"🌐 در حال باز کردن {url}...")
        await self.page.goto(url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        print("✅ وبسایت با موفقیت باز شد")
        
    async def fill_numbers(self, numbers: List[str], selectors: List[str]):
        """
        وارد کردن اعداد در فیلدها
        
        Args:
            numbers: لیست اعداد برای وارد کردن
            selectors: لیست سلکتورهای CSS/XPath برای فیلدها
        """
        print("📝 در حال وارد کردن اعداد...")
        
        for i, (number, selector) in enumerate(zip(numbers, selectors)):
            try:
                # منتظر میمونیم تا المنت در دسترس باشه
                await self.page.wait_for_selector(selector, state='visible')
                
                # پاک کردن فیلد قبلی
                await self.page.fill(selector, '')
                
                # وارد کردن عدد با تاخیر واقعی‌تر
                await self.page.type(selector, str(number), delay=100)
                
                print(f"  ✓ فیلد {i+1}: {number} وارد شد")
                
            except Exception as e:
                print(f"  ✗ خطا در وارد کردن فیلد {i+1}: {e}")
                raise
                
        await asyncio.sleep(0.5)  # تاخیر کوچک برای طبیعی‌تر بودن
        
    async def submit_form(self, submit_selector: str):
        """
        ارسال فرم
        
        Args:
            submit_selector: سلکتور دکمه سابمیت
        """
        print("🚀 در حال ارسال فرم...")
        
        try:
            # منتظر دکمه سابمیت
            await self.page.wait_for_selector(submit_selector, state='visible')
            
            # کلیک روی دکمه
            await self.page.click(submit_selector)
            
            # منتظر میمونیم تا navigation تموم بشه یا محتوا تغییر کنه
            try:
                await self.page.wait_for_load_state('networkidle', timeout=10000)
            except:
                await asyncio.sleep(2)  # اگر navigation نبود، کمی صبر میکنیم
                
            print("✅ فرم با موفقیت ارسال شد")
            
        except Exception as e:
            print(f"✗ خطا در ارسال فرم: {e}")
            raise
            
    async def extract_numbers(self, result_selectors: List[str]) -> List[str]:
        """
        خواندن اعداد از سایت
        
        Args:
            result_selectors: لیست سلکتورهای CSS/XPath برای خواندن نتایج
            
        Returns:
            لیست اعداد خوانده شده
        """
        print("📊 در حال خواندن اعداد از سایت...")
        
        results = []
        
        for i, selector in enumerate(result_selectors):
            try:
                # منتظر میمونیم تا المنت ظاهر بشه
                await self.page.wait_for_selector(selector, state='visible', timeout=15000)
                
                # خواندن محتوا
                element = await self.page.query_selector(selector)
                text = await element.inner_text()
                
                results.append(text.strip())
                print(f"  ✓ عدد {i+1}: {text.strip()}")
                
            except Exception as e:
                print(f"  ✗ خطا در خواندن عدد {i+1}: {e}")
                results.append(None)
                
        return results
        
    async def take_screenshot(self, filename: str = None):
        """
        گرفتن اسکرین‌شات از صفحه
        
        Args:
            filename: نام فایل (اگر None باشه، از تاریخ استفاده میکنه)
        """
        if filename is None:
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            
        await self.page.screenshot(path=filename, full_page=True)
        print(f"📸 اسکرین‌شات ذخیره شد: {filename}")
        
    async def close(self):
        """بستن مرورگر"""
        if self.browser:
            await self.browser.close()
            print("🔒 مرورگر بسته شد")


async def main():
    """تابع اصلی برنامه"""
    
    # ⚙️ تنظیمات - اینجا رو تغییر بده
    CONFIG = {
        'url': 'https://example.com',  # آدرس سایت
        'input_numbers': ['123', '456', '789'],  # اعدادی که میخوای وارد کنی
        'input_selectors': [
            '#input1',  # سلکتور فیلد اول
            '#input2',  # سلکتور فیلد دوم
            '#input3',  # سلکتور فیلد سوم
        ],
        'submit_selector': 'button[type="submit"]',  # سلکتور دکمه سابمیت
        'result_selectors': [
            '.result-1',  # سلکتور نتیجه اول
            '.result-2',  # سلکتور نتیجه دوم
        ],
        'headless': False,  # True = مرورگر نمایش داده نمیشه
        'take_screenshot': True  # True = اسکرین‌شات میگیره
    }
    
    # ساخت instance از کلاس
    automation = BrowserAutomation(headless=CONFIG['headless'])
    
    try:
        print("=" * 60)
        print("🤖 شروع اتومیشن مرورگر")
        print("=" * 60)
        
        # راه‌اندازی مرورگر
        await automation.initialize()
        
        # باز کردن وبسایت
        await automation.navigate_to_website(CONFIG['url'])
        
        # وارد کردن اعداد
        await automation.fill_numbers(
            CONFIG['input_numbers'],
            CONFIG['input_selectors']
        )
        
        # ارسال فرم
        await automation.submit_form(CONFIG['submit_selector'])
        
        # خواندن نتایج
        results = await automation.extract_numbers(CONFIG['result_selectors'])
        
        # نمایش نتایج
        print("\n" + "=" * 60)
        print("📋 نتایج نهایی:")
        print("=" * 60)
        for i, result in enumerate(results, 1):
            print(f"  نتیجه {i}: {result}")
        
        # ذخیره نتایج در فایل JSON
        output = {
            'timestamp': datetime.now().isoformat(),
            'url': CONFIG['url'],
            'inputs': CONFIG['input_numbers'],
            'results': results
        }
        
        with open('results.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print("\n💾 نتایج در results.json ذخیره شد")
        
        # گرفتن اسکرین‌شات
        if CONFIG['take_screenshot']:
            await automation.take_screenshot()
        
        print("\n✅ اتومیشن با موفقیت تمام شد!")
        
    except Exception as e:
        print(f"\n❌ خطا: {e}")
        # در صورت خطا، اسکرین‌شات بگیر
        try:
            await automation.take_screenshot('error_screenshot.png')
        except:
            pass
        raise
        
    finally:
        # بستن مرورگر
        await automation.close()


if __name__ == '__main__':
    # اجرای برنامه
    asyncio.run(main())
