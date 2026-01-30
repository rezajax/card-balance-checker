#!/usr/bin/env python3
"""
مثال‌های کاربردی برای استفاده از Browser Automation

این فایل شامل چند مثال واقعی برای کارهای مختلفه
"""

import asyncio
from advanced_automation import AdvancedBrowserAutomation


async def example_1_simple_form():
    """
    مثال 1: فرم ساده - وارد کردن اطلاعات و سابمیت
    """
    print("📝 مثال 1: فرم ساده")
    
    automation = AdvancedBrowserAutomation(headless=False)
    
    try:
        await automation.initialize()
        
        # باز کردن صفحه تست
        await automation.navigate_with_retry('https://www.google.com/search?q=test')
        
        # وارد کردن متن در search box
        await automation.smart_fill('textarea[name="q"]', 'Playwright automation')
        
        # کلیک روی دکمه جستجو (با Enter)
        await automation.page.keyboard.press('Enter')
        
        # انتظار برای نتایج
        await automation.wait_for_element('#search')
        
        # گرفتن اسکرین‌شات
        await automation.page.screenshot(path='example1_result.png')
        
        print("✅ مثال 1 تمام شد")
        
    finally:
        await automation.close()


async def example_2_extract_data():
    """
    مثال 2: استخراج داده از چند المنت
    """
    print("📊 مثال 2: استخراج داده")
    
    automation = AdvancedBrowserAutomation(headless=False)
    
    try:
        await automation.initialize()
        
        # باز کردن یک صفحه نمونه
        await automation.navigate_with_retry('https://example.com')
        
        # استخراج داده‌ها
        data = await automation.extract_data({
            'title': 'h1',
            'description': 'p',
        })
        
        print("📋 داده‌های استخراج شده:")
        for key, value in data.items():
            print(f"  {key}: {value}")
            
        # ذخیره نتایج
        await automation.save_results(data, 'example2_data.json')
        
        print("✅ مثال 2 تمام شد")
        
    finally:
        await automation.close()


async def example_3_multiple_pages():
    """
    مثال 3: پیمایش در چند صفحه
    """
    print("🔄 مثال 3: چند صفحه")
    
    automation = AdvancedBrowserAutomation(headless=False)
    
    try:
        await automation.initialize()
        
        urls = [
            'https://example.com',
            'https://example.org',
        ]
        
        all_data = []
        
        for i, url in enumerate(urls, 1):
            print(f"صفحه {i}/{len(urls)}: {url}")
            
            await automation.navigate_with_retry(url)
            
            # استخراج عنوان
            title = await automation.page.title()
            print(f"  عنوان: {title}")
            
            all_data.append({
                'url': url,
                'title': title
            })
            
            await asyncio.sleep(1)  # تاخیر بین درخواست‌ها
            
        # ذخیره همه داده‌ها
        await automation.save_results(all_data, 'example3_all_pages.json')
        
        print("✅ مثال 3 تمام شد")
        
    finally:
        await automation.close()


async def example_4_wait_for_dynamic_content():
    """
    مثال 4: انتظار برای محتوای داینامیک (AJAX)
    """
    print("⏳ مثال 4: محتوای داینامیک")
    
    automation = AdvancedBrowserAutomation(headless=False)
    
    try:
        await automation.initialize()
        
        await automation.navigate_with_retry('https://example.com')
        
        # انتظار برای المنت خاص (مثلا بعد از AJAX load میشه)
        element_appeared = await automation.wait_for_element(
            'div.loaded-content',  # سلکتور المنتی که بعد از load ظاهر میشه
            timeout=15000
        )
        
        if element_appeared:
            print("✅ محتوای داینامیک لود شد")
            
            # حالا میتونیم داده رو استخراج کنیم
            data = await automation.extract_data({
                'dynamic_content': 'div.loaded-content'
            })
            print(f"محتوا: {data}")
        else:
            print("❌ محتوای داینامیک لود نشد")
            
        print("✅ مثال 4 تمام شد")
        
    finally:
        await automation.close()


async def example_5_handle_dropdowns_and_checkboxes():
    """
    مثال 5: کار با dropdown، checkbox و radio button
    """
    print("🎛️ مثال 5: Dropdown و Checkbox")
    
    automation = AdvancedBrowserAutomation(headless=False)
    
    try:
        await automation.initialize()
        
        # فرض کن یک فرم با dropdown و checkbox داریم
        await automation.navigate_with_retry('https://example.com/form')
        
        # انتخاب از dropdown
        await automation.page.select_option('select#country', 'iran')
        print("✓ کشور انتخاب شد")
        
        # چک کردن checkbox
        await automation.page.check('input#agree-terms')
        print("✓ Checkbox چک شد")
        
        # انتخاب radio button
        await automation.page.check('input[name="gender"][value="male"]')
        print("✓ Radio button انتخاب شد")
        
        # سابمیت فرم
        await automation.smart_click('button[type="submit"]', wait_for_navigation=True)
        
        print("✅ مثال 5 تمام شد")
        
    finally:
        await automation.close()


async def example_6_handle_alerts():
    """
    مثال 6: کار با alert، confirm و prompt
    """
    print("⚠️ مثال 6: Alerts")
    
    automation = AdvancedBrowserAutomation(headless=False)
    
    try:
        await automation.initialize()
        
        # تنظیم handler برای dialog
        automation.page.on('dialog', lambda dialog: asyncio.create_task(dialog.accept()))
        
        # باز کردن صفحه‌ای که alert داره
        await automation.navigate_with_retry('https://example.com')
        
        # کلیک روی دکمه‌ای که alert نشون میده
        # await automation.page.click('#show-alert')
        
        print("✅ مثال 6 تمام شد")
        
    finally:
        await automation.close()


async def example_7_file_upload():
    """
    مثال 7: آپلود فایل
    """
    print("📤 مثال 7: آپلود فایل")
    
    automation = AdvancedBrowserAutomation(headless=False)
    
    try:
        await automation.initialize()
        
        await automation.navigate_with_retry('https://example.com/upload')
        
        # انتخاب فایل برای آپلود
        await automation.page.set_input_files(
            'input[type="file"]',
            'path/to/your/file.txt'
        )
        print("✓ فایل انتخاب شد")
        
        # کلیک روی دکمه آپلود
        await automation.smart_click('button.upload')
        
        print("✅ مثال 7 تمام شد")
        
    finally:
        await automation.close()


async def example_8_scroll_and_infinite_load():
    """
    مثال 8: اسکرول و بارگذاری بینهایت (infinite scroll)
    """
    print("📜 مثال 8: Infinite Scroll")
    
    automation = AdvancedBrowserAutomation(headless=False)
    
    try:
        await automation.initialize()
        
        await automation.navigate_with_retry('https://example.com/infinite-scroll')
        
        # اسکرول کردن چند بار
        for i in range(5):
            print(f"اسکرول {i+1}/5")
            
            # اسکرول به پایین صفحه
            await automation.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            
            # انتظار برای لود شدن محتوای جدید
            await asyncio.sleep(2)
            
        # حالا همه محتوا لود شده، میتونیم استخراج کنیم
        items = await automation.page.query_selector_all('.item')
        print(f"✓ {len(items)} آیتم لود شد")
        
        print("✅ مثال 8 تمام شد")
        
    finally:
        await automation.close()


async def example_9_hover_and_nested_menus():
    """
    مثال 9: Hover و منوهای تودرتو
    """
    print("🖱️ مثال 9: Hover Menu")
    
    automation = AdvancedBrowserAutomation(headless=False)
    
    try:
        await automation.initialize()
        
        await automation.navigate_with_retry('https://example.com')
        
        # Hover روی منوی اصلی
        await automation.page.hover('#main-menu')
        await asyncio.sleep(0.5)
        
        # حالا submenu ظاهر شده، میتونیم کلیک کنیم
        await automation.page.click('#submenu-item')
        
        print("✅ مثال 9 تمام شد")
        
    finally:
        await automation.close()


async def example_10_parallel_browsers():
    """
    مثال 10: اجرای موازی چند مرورگر
    """
    print("🚀 مثال 10: Parallel Browsers")
    
    async def process_url(url: str, browser_num: int):
        automation = AdvancedBrowserAutomation(headless=True)
        try:
            await automation.initialize()
            await automation.navigate_with_retry(url)
            title = await automation.page.title()
            print(f"Browser {browser_num}: {title}")
            return title
        finally:
            await automation.close()
    
    # اجرای موازی
    urls = [
        'https://example.com',
        'https://example.org',
        'https://example.net',
    ]
    
    tasks = [process_url(url, i+1) for i, url in enumerate(urls)]
    results = await asyncio.gather(*tasks)
    
    print(f"✅ {len(results)} مرورگر به صورت موازی اجرا شدند")


def main():
    """منوی اصلی برای انتخاب مثال"""
    
    examples = {
        '1': ('فرم ساده', example_1_simple_form),
        '2': ('استخراج داده', example_2_extract_data),
        '3': ('چند صفحه', example_3_multiple_pages),
        '4': ('محتوای داینامیک', example_4_wait_for_dynamic_content),
        '5': ('Dropdown و Checkbox', example_5_handle_dropdowns_and_checkboxes),
        '6': ('Alerts', example_6_handle_alerts),
        '7': ('آپلود فایل', example_7_file_upload),
        '8': ('Infinite Scroll', example_8_scroll_and_infinite_load),
        '9': ('Hover Menu', example_9_hover_and_nested_menus),
        '10': ('Parallel Browsers', example_10_parallel_browsers),
    }
    
    print("\n" + "="*50)
    print("🎯 مثال‌های Browser Automation")
    print("="*50)
    
    for key, (name, _) in examples.items():
        print(f"  {key}. {name}")
    
    print("\n  0. خروج")
    print("="*50)
    
    choice = input("\nشماره مثال را انتخاب کنید: ").strip()
    
    if choice == '0':
        print("خداحافظ! 👋")
        return
    
    if choice in examples:
        name, func = examples[choice]
        print(f"\n🚀 اجرای مثال: {name}\n")
        asyncio.run(func())
    else:
        print("❌ انتخاب نامعتبر!")


if __name__ == '__main__':
    main()
