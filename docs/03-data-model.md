# ۳. مدل داده

SQLite، از طریق SQLAlchemy 2.x. همه‌ی مبالغ **عدد صحیح ریال** (`INTEGER`) هستند. تاریخ‌ها به دو شکل نگه داشته می‌شوند: `date` میلادی (ISO) برای مرتب‌سازی، و نمایش شمسی که با `jdatetime` ساخته می‌شود. متن‌ها UTF-8 هستند و قبل از ذخیره نرمال می‌شوند: «ي/ك» عربی به «ی/ک» و ارقام فارسی و عربی به لاتین.

هر جدول این ستون‌ها را دارد: `id INTEGER PK`، `created_at`، `updated_at` و `is_archived BOOL`. حذف همیشه نرم (soft delete) است.

## ۳.۱ اطلاعات پایه

### issuer — صادرکننده / سربرگ
| فیلد | نوع | توضیح |
|---|---|---|
| code | text unique | `PERSONAL`, `COMPANY` |
| kind | enum | `personal` / `company` |
| title | text | نام نمایشی در برنامه |
| name, signer_name, signer_title | text | در خروجی |
| national_id, economic_code, registration_no | text | |
| phone, mobile, fax, address, postal_code | text | |
| vat_enabled_by_default | bool | شرکتی: بله |
| default_vat_percent | numeric(5,2) | ۱۰ |
| show_stamp_by_default | bool | |
| stamp_image, signature_image | path | در پوشه‌ی داده |
| letter_template, proforma_template, invoice_template, statement_template | text | نام فایل در `templates/` |
| number_pattern, number_scope | text | سند ۰۵ |

### account — حساب بانکی
`code, issuer_id (nullable), bank, branch, holder, iban (26 char), account_no, card_no, active, notes`
- اعتبارسنجی IBAN (mod-97) هنگام ذخیره الزامی است.
- نمایش شبا: چهار رقم چهار رقم، مثل `IR74 0190 0000 0011 8420 3320 08`.

### party — شخص / شرکت (طرف حساب)
`code, kind (company/person/bank/government), name, short_name, archive_folder, national_id, economic_code, registration_no, address, postal_code, phone, fax, notes`

### contact — مخاطب
`party_id, title_prefix (جناب آقای/سرکار خانم), honorific (مهندس/دکتر/—), name, position (مدیرعامل، مدیر بازرگانی، …), phone, is_default`

### letter_type — موضوع نامه
`code, category, title, subject_line, body (JSON: list of paragraph templates), fields (JSON schema), closing, with_items_table, with_clauses, with_account`
- جای‌خالی‌ها `{name}` هستند و با فیلدهای همان نوع، به‌علاوه‌ی متغیرهای عمومی پر می‌شوند (سند ۰۵ ‎§۵.۴).

### clause — بند
`code, group (payment/delivery/tax/site/other/note), text, variables (JSON), applies_to (JSON list), default_for_issuers (JSON list), requires (JSON), excludes (JSON list), sort_order, usage_count`

### party_clause_default — بندهای پیش‌فرض هر مشتری
`party_id, clause_id, doc_kind`
- بندی که سه بار برای یک مشتری تیک خورده باشد، دفعه‌ی بعد پیشنهاد می‌شود. این ردیف به‌طور خودکار پر می‌شود.

### item — کاتالوگ اقلام و خدمات
`code, category, description, unit, last_unit_price, last_price_date, last_price_source, last_purchase_price (پنهان), buyer_supplied_by_default`

### unit — واحدها
`name`

## ۳.۲ پروژه و سند

### project — پروژه (پوشه)
| فیلد | توضیح |
|---|---|
| party_id | مشتری |
| title | «سیستم سوخت گازوئیل ۱۷ مشعل» |
| status | `open` / `waiting_payment` / `retention` / `closed` / `cancelled` |
| contract_no, contract_date | از قرارداد کارفرما |
| contract_amount | ریال |
| retention_percent, retention_months | پیش‌فرض ۱۰٪ و ۳ ماه |
| handover_date | تحویل موقت |
| supplier_name, supplier_notes | داخلی؛ هرگز در خروجی نمی‌آید |
| folder_path | مسیر پوشه روی دیسک |

### document — سند
| فیلد | توضیح |
|---|---|
| kind | `letter` / `proforma` / `invoice` / `statement` / `attachment_list` |
| issuer_id, party_id, contact_id, project_id | |
| letter_type_id | فقط برای نامه |
| number | رشته‌ی نهایی، مثل «014/1405» |
| seq, seq_year, seq_month | برای یکتایی؛ unique (issuer, kind-group, year, seq) |
| date_greg, date_jalali | |
| title | «پیش‌فاکتور فروش و خدمات» / «فاکتور فروش و خدمات» / «صورت وضعیت» |
| subject, salutation, closing, attachment_text | نامه |
| fields_json | مقادیر فیلدهای موضوع نامه |
| body_override | متن نهایی اگر کاربر دستی ویرایش کرده باشد |
| vat_enabled, vat_percent, insurance_note | |
| input_currency | `rial` / `toman` / `million_toman` (فقط برای ورود داده) |
| subtotal, vat_amount, payable | ریال؛ محاسبه و ذخیره‌شده |
| show_stamp, show_signature | |
| status | `draft` / `issued` / `sent` / `accepted` / `rejected` / `paid` / `void` |
| parent_document_id | مثلاً فاکتوری که از پیش‌فاکتور ساخته شده |
| tax_serial | شماره‌ی منحصربه‌فرد مالیاتی (اختیاری) |

### document_line — ردیف اقلام
`document_id, idx, item_id (nullable), description, unit, qty (numeric), unit_price (int rial), purchase_price (int, hidden), markup_percent, total (int), buyer_supplied (bool), emphasis (bool), note`

### document_clause — بندهای انتخاب‌شده
`document_id, clause_id (nullable for ad-hoc), group, sort_order, rendered_text (snapshot), variables_json`
- متن نهایی بند در لحظه‌ی صدور در `rendered_text` کپی می‌شود. اگر کتابخانه‌ی بندها بعداً عوض شود، سند قدیمی دست نمی‌خورد.

### document_account
`document_id, account_id, sort_order`

### document_file — فایل‌های تولیدشده و پیوست
`document_id, role (docx/pdf/merged_pdf/attachment_drawing/attachment_other), path, version, sha256, created_at`

## ۳.۳ تسک‌ها

### task
`title, project_id, document_id (nullable), party_id, due_date, status (open/done/cancelled), source (manual/auto:<rule_code>), notes, done_at`

## ۳.۴ تنظیمات و سیستم

### setting
`key, value_json` — مقادیر اولیه از `seed/settings.json` می‌آید.

### number_counter
`issuer_id, group, period_key, last_seq`
- `group` یکی از `letter` یا `invoice_family` است. پیش‌فاکتور، فاکتور و صورت‌وضعیت در `invoice_family` مشترک‌اند، مگر تنظیم دیگری انتخاب شود.

### audit_log
`at, action, entity, entity_id, summary`

### archive_file — بایگانی قدیمی (فاز ۲)
`party_id, path, kind_guess, date_guess, title`
- از اسکن پوشه‌ی قدیمی آرشیو پر می‌شود و فقط لینک باز کردن فایل را نگه می‌دارد.

## ۳.۵ بارگذاری اولیه

در اولین اجرا، اگر جدول `issuer` خالی باشد، فایل‌های `seed/*.json` به ترتیب `units`، `issuers`، `accounts`، `parties` (همراه مخاطبان)، `letter_types`، `clauses`، `items` و `settings` وارد می‌شوند. این کار idempotent است: کلید هر رکورد `code` است.

تصاویر `assets/stamp_company.jpg` و `assets/signature_bahrami.png` به پوشه‌ی داده کپی و به صادرکننده‌ها وصل می‌شوند.
