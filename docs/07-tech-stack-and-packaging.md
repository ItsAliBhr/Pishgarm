# ۷. فناوری، ساختار پروژه و نصب روی ویندوز

## ۷.۱ چرا این انتخاب

| نیاز | انتخاب | دلیل |
|---|---|---|
| نصب ساده روی ویندوز پدر، بدون اینترنت و بدون سرور | برنامه‌ی دسکتاپ با نصب‌کننده‌ی `Setup.exe` | یک بار نصب، آیکون روی دسکتاپ؛ داده روی همان کامپیوتر می‌ماند |
| رابط فارسی راست‌به‌چپ تمیز | **PySide6 (Qt 6)** | پشتیبانی بومی RTL، جدول، Combo جست‌وجوپذیر و فونت سفارشی؛ لایسنس LGPL |
| تولید Word از قالب واقعی | **docxtpl** (روی python-docx + Jinja2) | قالب‌ها همین حالا با این نحو ساخته شده‌اند |
| تاریخ شمسی، اعداد فارسی، حروف | `jdatetime` + ماژول داخلی `num2words_fa` با تست | کتابخانه‌های جاافتاده، بدون وابستگی سنگین |
| پایگاه داده | **SQLite** + SQLAlchemy 2.x | یک فایل؛ پشتیبان‌گیری با کپی |
| PDF | Word COM (`pywin32`/`docx2pdf`)؛ fallback به LibreOffice؛ `pypdf` برای ادغام؛ `pypdfium2` برای رندر و پاک کردن ناحیه | خروجی PDF دقیقاً مثل Word خود کاربر |
| بسته‌بندی | **PyInstaller** (one-folder) + **Inno Setup** | Setup فارسی، میان‌بر دسکتاپ، حذف و نصب تمیز |

**گزینه‌هایی که کنار گذاشته شدند:**
- **وب‌اپ:** نیاز به سرور یا اجرای پس‌زمینه دارد و برای پدر پیچیده‌تر است.
- **Electron:** حجم زیاد، و تولید Word در JS ضعیف‌تر است.
- **Oracle APEX:** نیاز به پایگاه داده‌ی Oracle و سرور دارد.
- **‎.NET/WPF:** تولید docx از قالب Word در .NET دشوارتر است و کتابخانه‌های فارسی کمتری دارد.

**حداقل سیستم:** ویندوز ۱۰ یا ۱۱، ۶۴ بیتی. PySide6 و Python 3.12 روی ویندوز ۷ و ۸ اجرا نمی‌شوند (سؤال باز در سند ۰۸). Microsoft Word برای PDF دقیق توصیه می‌شود ولی الزامی نیست.

## ۷.۲ ساختار پروژه

```
pishgarm-docs/
  app/
    __main__.py            # اجرای برنامه
    core/                  # منطق خالص، بدون Qt
      money.py             # ریال/تومان، جمع، ارزش افزوده، مارک‌آپ
      num2words_fa.py      # عدد به حروف + تست
      jalali.py            # تاریخ شمسی، روز کاری
      validators.py        # شبا، شناسه ملی، کد ملی، کد پستی
      numbering.py         # الگو و شمارنده
      clauses.py           # جایگذاری متغیر، قواعد سازگاری
      letters.py           # ساخت addressee_lines, subject, body_paragraphs
      context.py           # ساخت context برای هر قالب (سند ۰۵)
      render.py            # docxtpl → docx ؛ PDF ؛ ادغام
      pdf_tools.py         # تصویر→PDF، هم‌اندازه‌سازی، پاک کردن ناحیه
      tasks.py             # قواعد تسک خودکار
      files.py             # مسیر، نام فایل، نسخه
    db/
      models.py            # SQLAlchemy
      seed.py              # بارگذاری seed/*.json
      migrations.py        # نسخه‌ی schema ساده (PRAGMA user_version)
      backup.py
    ui/
      main_window.py, widgets/ (jalali_date_edit.py, money_edit.py, search_combo.py, clause_picker.py)
      pages/ (home, documents, projects, tasks, master_data/*, settings)
      wizard/ (step_type, step_issuer, step_party, step_content, step_clauses, step_output)
    resources/fonts/Vazirmatn-*.ttf, icons/
  templates/  seed/  assets/
  tests/       # pytest: core + render tests with templates/test_contexts
  tools/build_windows.py, installer.iss
  pyproject.toml
```

## ۷.۳ نکته‌های پیاده‌سازی

- **RTL:** `app.setLayoutDirection(Qt.RightToLeft)`. فونت پیش‌فرض برنامه Vazirmatn است. جدول‌ها ستون اول (#) را سمت راست دارند.
- **ورودی تاریخ شمسی:** `QCalendarWidget` شمسی نمی‌فهمد. یک ویجت ساده با سه Combo (روز، ماه، سال) و یک popup تقویم ماهانه‌ی شمسی بسازید.
- **ورودی پول (`MoneyEdit`):**
  - QLineEdit با validator و جداکننده‌ی زنده
  - Combo واحد (ریال / تومان / میلیون تومان)
  - برچسب زیرین: «= ۲۱٬۰۰۰٬۰۰۰٬۰۰۰ ریال – بیست و یک میلیارد ریال»
- **رندر:** `DocxTemplate(path).render(context, autoescape=True)`. تصویر امضای قالب شخصی با `InlineImage` داده می‌شود.
- **رندر در پس‌زمینه:** تبدیل به PDF در یک `QThread` با نوار پیشرفت انجام شود تا رابط قفل نشود.
- **مسیر داده:**
  - پایگاه داده: `%LOCALAPPDATA%\PishgarmDocs\data.db`
  - تصاویر مهر و امضا: `%LOCALAPPDATA%\PishgarmDocs\assets\`
  - قالب‌ها: کپی کاربرپذیر در `%LOCALAPPDATA%\PishgarmDocs\templates\`. اگر کاربر قالبی را عوض کرد، نسخه‌ی او اولویت دارد. دکمه‌ی «بازگردانی قالب پیش‌فرض» هم باشد.
- **پشتیبان:**
  - هنگام بستن برنامه و روزی یک بار، `data.db` به `Documents\اسناد پیشگرم\_پشتیبان\data-1405-09-01.db` کپی می‌شود. ۳۰ نسخه‌ی آخر نگه داشته می‌شود.
  - دکمه‌ی «پشتیبان‌گیری روی فلش».
- **لاگ:** `%LOCALAPPDATA%\PishgarmDocs\logs\app.log` (چرخشی). خطاها پیام فارسی ساده و دکمه‌ی «کپی جزئیات» دارند.
- **به‌روزرسانی:** نسخه‌ی جدید با اجرای Setup جدید روی قبلی نصب می‌شود. داده در `%LOCALAPPDATA%` است، پس دست نمی‌خورد. migration در اولین اجرا انجام می‌شود.

## ۷.۴ ساخت نصب‌کننده

PyInstaller نمی‌تواند از مک یا لینوکس خروجی ویندوز بسازد. ساخت روی ویندوز یا GitHub Actions انجام می‌شود:

```yaml
# .github/workflows/build-windows.yml
on: [workflow_dispatch, push]
jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -e .[build]
      - run: pytest
      - run: pyinstaller app.spec --noconfirm
      - run: choco install innosetup -y
      - run: iscc tools/installer.iss
      - uses: actions/upload-artifact@v4
        with: { name: PishgarmDocsSetup, path: dist/PishgarmDocsSetup.exe }
```

- `app.spec` باید `templates/`، `seed/`، `assets/` و `app/resources/` را به‌عنوان data کپی کند.
- `installer.iss`:
  - زبان فارسی (Inno Setup فایل `Farsi.isl` دارد)
  - نصب در `{autopf}\PishgarmDocs`
  - میان‌بر دسکتاپ با نام «دفتر اسناد پیشگرم»
  - بدون نیاز به دسترسی ادمین (`PrivilegesRequired=lowest`)
- اگر Windows SmartScreen هشدار داد، یک بار «More info ← Run anyway» لازم است. امضای کد اختیاری است.

## ۷.۵ وابستگی‌ها (`pyproject.toml`)

```
PySide6>=6.7, SQLAlchemy>=2.0, docxtpl>=0.18, python-docx>=1.1, jdatetime>=5.0,
pypdf>=4.0, pypdfium2>=4.0, Pillow>=10, pywin32; sys_platform=='win32'
[build] pyinstaller>=6.6
[dev] pytest
```
