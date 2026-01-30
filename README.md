# 🤖 Browser Automation با Playwright

پروژه اتومیشن مرورگر با استفاده از بهترین تکنولوژی‌ها برای Arch Linux

## 🚀 ویژگی‌ها

- ✅ استفاده از **Playwright** (سریع‌ترین و پایدارترین ابزار اتومیشن)
- ✅ **Async/Await** برای بهترین performance
- ✅ پشتیبانی از **Chromium, Firefox, WebKit**
- ✅ **Retry mechanism** برای handling خطاها
- ✅ **Smart selectors** با fallback
- ✅ **Logging** کامل و حرفه‌ای
- ✅ پنهان کردن **automation detection**
- ✅ گرفتن **screenshot** و ذخیره نتایج در JSON
- ✅ تنظیمات از طریق **environment variables**

## 📦 نصب و راه‌اندازی

### 1. نصب Python dependencies

```bash
# نصب pip اگر نداری
sudo pacman -S python-pip

# نصب کتابخانه‌ها
pip install -r requirements.txt

# نصب مرورگرهای Playwright
playwright install

# (اختیاری) نصب dependencies سیستمی
playwright install-deps
```

### 2. تنظیم پروژه

```bash
# کپی فایل نمونه تنظیمات
cp .env.example .env

# ویرایش تنظیمات
nano .env
```

## 🎯 استفاده

### نسخه ساده

```bash
python browser_automation.py
```

این فایل رو قبل از اجرا ویرایش کن و بخش `CONFIG` رو تغییر بده:

```python
CONFIG = {
    'url': 'https://your-website.com',  # آدرس سایت
    'input_numbers': ['123', '456', '789'],  # اعدادی که میخوای وارد کنی
    'input_selectors': ['#field1', '#field2', '#field3'],  # سلکتورهای فیلدها
    'submit_selector': 'button[type="submit"]',  # دکمه سابمیت
    'result_selectors': ['.result1', '.result2'],  # المنت‌های نتیجه
}
```

### نسخه پیشرفته (توصیه میشه)

```bash
python advanced_automation.py
```

این نسخه تنظیمات رو از فایل `.env` میخونه و قابلیت‌های بیشتری داره.

## ⚙️ تنظیمات

### چطور سلکتورها رو پیدا کنم؟

1. **باز کردن Developer Tools** در مرورگر: `F12`
2. **کلیک روی آیکون Inspect** (گوشه بالا سمت چپ)
3. **کلیک روی المنت** مورد نظر در صفحه
4. **راست کلیک روی HTML** در Developer Tools
5. **Copy > Copy selector**

### انواع سلکتورها

```python
# CSS Selectors
'#my-id'              # ID
'.my-class'           # Class
'input[name="field"]' # Attribute
'button[type="submit"]' # Button

# XPath (برای موارد پیچیده)
'xpath=//button[contains(text(), "ارسال")]'

# Text (برای متن)
'text=ارسال فرم'
```

## 📊 خروجی‌ها

پس از اجرا، فایل‌های زیر ساخته میشن:

- `results.json` - نتایج استخراج شده
- `screenshot_*.png` - اسکرین‌شات از صفحه
- `automation.log` - لاگ‌های اجرا
- `error_screenshot.png` - در صورت بروز خطا

## 🛠️ مثال کامل

فرض کن یک سایت داریم که میخوایم:
1. سه تا عدد وارد کنیم
2. فرم رو سابمیت کنیم
3. دو تا نتیجه رو بخونیم

```python
CONFIG = {
    'url': 'https://calculator-example.com',
    'input_numbers': ['10', '20', '30'],
    'input_selectors': [
        '#number1',
        '#number2', 
        '#number3'
    ],
    'submit_selector': 'button.calculate',
    'result_selectors': [
        '#sum-result',
        '#average-result'
    ]
}
```

## 🎨 قابلیت‌های پیشرفته

### 1. تغییر نوع مرورگر

```python
await automation.initialize(browser_type='firefox')  # یا webkit
```

### 2. حالت Headless

```python
automation = AdvancedBrowserAutomation(headless=True)
```

### 3. Slow Motion برای Debug

```python
automation = AdvancedBrowserAutomation(slow_mo=500)  # 500ms تاخیر
```

### 4. استخراج داده‌های پیچیده‌تر

```python
results = await automation.extract_data({
    'title': 'h1.page-title',
    'price': '.product-price',
    'description': '#product-desc',
    'rating': '.star-rating'
})
```

## 🔧 رفع مشکلات رایج

### مشکل 1: المنت پیدا نمیشه

```python
# استفاده از انتظار بیشتر
await automation.wait_for_element('#my-element', timeout=60000)

# یا استفاده از XPath
selector = 'xpath=//div[contains(@class, "my-class")]'
```

### مشکل 2: سایت تشخیص میده که بات هست

```python
# این قابلیت‌ها در کد موجوده:
# - پنهان کردن navigator.webdriver
# - User agent واقعی
# - Viewport و timezone مناسب
```

### مشکل 3: صفحه خیلی کند لود میشه

```python
# تغییر تایم‌اوت
self.page.set_default_timeout(60000)  # 60 ثانیه

# یا صبر کردن برای المنت خاص
await automation.wait_for_element('.loaded-indicator')
```

## 📚 منابع بیشتر

- [Playwright Documentation](https://playwright.dev/python/)
- [CSS Selectors Reference](https://www.w3schools.com/cssref/css_selectors.php)
- [XPath Tutorial](https://www.w3schools.com/xml/xpath_intro.asp)

## 🤝 کمک و پشتیبانی

اگر مشکلی داشتی:
1. لاگ `automation.log` رو بررسی کن
2. `error_screenshot.png` رو نگاه کن
3. با `headless=False` اجرا کن تا ببینی چه اتفاقی می‌افته

## 📝 نکات مهم

- ✅ همیشه سلکتورها رو قبل از اجرا تست کن
- ✅ برای سایت‌های واقعی، از `time.sleep()` بین درخواست‌ها استفاده کن
- ✅ احترام به `robots.txt` و terms of service سایت‌ها
- ✅ برای production، از proxy و user agent rotation استفاده کن

---

**ساخته شده با ❤️ برای Arch Linux**
