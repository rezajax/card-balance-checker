#!/bin/bash
# اسکریپت نصب و راه‌اندازی خودکار

echo "🚀 شروع نصب Browser Automation..."
echo "================================"

# رنگ‌ها برای خروجی
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# تابع برای نمایش پیام‌ها
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# چک کردن Python
print_info "چک کردن Python..."
if ! command -v python3 &> /dev/null; then
    print_error "Python3 نصب نیست"
    print_info "در حال نصب Python..."
    sudo pacman -S python python-pip --noconfirm
else
    print_success "Python $(python3 --version) نصب است"
fi

# چک کردن pip
print_info "چک کردن pip..."
if ! command -v pip &> /dev/null; then
    print_error "pip نصب نیست"
    sudo pacman -S python-pip --noconfirm
else
    print_success "pip نصب است"
fi

# نصب dependencies
print_info "نصب Python packages..."
pip install -r requirements.txt --user

if [ $? -eq 0 ]; then
    print_success "Packages با موفقیت نصب شدند"
else
    print_error "خطا در نصب packages"
    exit 1
fi

# نصب Playwright browsers
print_info "نصب مرورگرهای Playwright (ممکنه کمی طول بکشه)..."
python3 -m playwright install chromium

if [ $? -eq 0 ]; then
    print_success "مرورگر Chromium نصب شد"
else
    print_error "خطا در نصب مرورگر"
    exit 1
fi

# نصب dependencies سیستمی برای Playwright (اختیاری)
print_info "نصب dependencies سیستمی..."
python3 -m playwright install-deps

# ساخت فایل .env اگر وجود نداره
if [ ! -f .env ]; then
    print_info "ساخت فایل .env..."
    cp .env.example .env
    print_success "فایل .env ساخته شد - حتما آن را ویرایش کنید!"
else
    print_info "فایل .env موجود است"
fi

# ساخت پوشه‌های مورد نیاز
mkdir -p screenshots
mkdir -p results
mkdir -p logs

# اجرای تست ساده
echo ""
print_info "آیا میخواهید یک تست ساده اجرا کنید؟ (y/n)"
read -r response
if [[ "$response" == "y" ]] || [[ "$response" == "Y" ]]; then
    print_info "اجرای تست..."
    python3 -c "from playwright.sync_api import sync_playwright; print('✅ Playwright به درستی نصب شده است')"
    
    if [ $? -eq 0 ]; then
        print_success "تست موفقیت‌آمیز بود!"
    else
        print_error "تست ناموفق - لطفا خطاها رو بررسی کنید"
    fi
fi

echo ""
echo "================================"
print_success "نصب تمام شد!"
echo ""
echo "📝 مراحل بعدی:"
echo "  1. فایل .env را ویرایش کنید:"
echo "     nano .env"
echo ""
echo "  2. برای نسخه ساده:"
echo "     python3 browser_automation.py"
echo ""
echo "  3. برای نسخه پیشرفته:"
echo "     python3 advanced_automation.py"
echo ""
echo "  4. برای اطلاعات بیشتر:"
echo "     cat README.md"
echo ""
print_success "موفق باشید! 🚀"
