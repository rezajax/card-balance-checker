#!/usr/bin/env python3
"""
تست نصب و راه‌اندازی Playwright
این اسکریپت برای چک کردن اینکه همه چیز درست نصب شده
"""

import sys
import asyncio


def check_imports():
    """چک کردن import شدن کتابخانه‌ها"""
    print("🔍 در حال چک کردن کتابخانه‌ها...")
    
    try:
        import playwright
        print("  ✅ playwright")
    except ImportError:
        print("  ❌ playwright - نصب نشده!")
        print("     نصب: pip install playwright")
        return False
        
    try:
        import dotenv
        print("  ✅ python-dotenv")
    except ImportError:
        print("  ⚠️  python-dotenv - نصب نشده (اختیاری)")
        
    try:
        import aiofiles
        print("  ✅ aiofiles")
    except ImportError:
        print("  ⚠️  aiofiles - نصب نشده (اختیاری)")
        
    return True


async def test_browser():
    """تست باز شدن مرورگر"""
    print("\n🌐 در حال تست مرورگر...")
    
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            # تست Chromium
            print("  📱 تست Chromium...")
            try:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto('https://example.com')
                title = await page.title()
                await browser.close()
                print(f"  ✅ Chromium: صفحه با عنوان '{title}' باز شد")
            except Exception as e:
                print(f"  ❌ Chromium: {e}")
                print("     نصب: python -m playwright install chromium")
                return False
                
        return True
        
    except Exception as e:
        print(f"  ❌ خطا: {e}")
        return False


async def test_automation_class():
    """تست کلاس اتومیشن"""
    print("\n🤖 در حال تست کلاس اتومیشن...")
    
    try:
        from advanced_automation import AdvancedBrowserAutomation
        
        automation = AdvancedBrowserAutomation(headless=True)
        await automation.initialize()
        
        # تست navigation
        await automation.navigate_with_retry('https://example.com')
        
        # تست استخراج داده
        data = await automation.extract_data({
            'title': 'h1',
            'text': 'p'
        })
        
        print(f"  ✅ داده استخراج شد: title={data.get('title', 'N/A')[:30]}...")
        
        await automation.close()
        
        return True
        
    except Exception as e:
        print(f"  ❌ خطا: {e}")
        import traceback
        traceback.print_exc()
        return False


def print_summary(results):
    """نمایش خلاصه نتایج"""
    print("\n" + "="*60)
    print("📊 خلاصه نتایج:")
    print("="*60)
    
    for test_name, result in results.items():
        status = "✅ موفق" if result else "❌ ناموفق"
        print(f"  {test_name}: {status}")
        
    print("="*60)
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n🎉 همه چیز آماده است! میتونی شروع کنی:")
        print("\n  نسخه ساده:")
        print("    python browser_automation.py")
        print("\n  نسخه پیشرفته:")
        print("    python advanced_automation.py")
        print("\n  مثال‌ها:")
        print("    python example_usage.py")
    else:
        print("\n⚠️  برخی تست‌ها ناموفق بودند.")
        print("لطفا خطاهای بالا رو بررسی کنید و مشکلات رو حل کنید.")
        print("\nبرای نصب:")
        print("  ./setup.sh")
        print("یا:")
        print("  pip install -r requirements.txt")
        print("  python -m playwright install chromium")


async def main():
    """تابع اصلی"""
    print("="*60)
    print("🧪 تست نصب Browser Automation")
    print("="*60)
    
    results = {}
    
    # تست 1: Import ها
    results['کتابخانه‌ها'] = check_imports()
    
    if not results['کتابخانه‌ها']:
        print("\n❌ لطفا اول کتابخانه‌های مورد نیاز رو نصب کنید:")
        print("  pip install -r requirements.txt")
        sys.exit(1)
    
    # تست 2: مرورگر
    results['مرورگر'] = await test_browser()
    
    # تست 3: کلاس اتومیشن (فقط اگه مرورگر کار کرد)
    if results['مرورگر']:
        results['کلاس اتومیشن'] = await test_automation_class()
    else:
        results['کلاس اتومیشن'] = False
        print("  ⏭️  رد شد (به دلیل مشکل مرورگر)")
    
    # نمایش خلاصه
    print_summary(results)
    
    # Return code
    sys.exit(0 if all(results.values()) else 1)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  تست توسط کاربر لغو شد")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ خطای غیرمنتظره: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
