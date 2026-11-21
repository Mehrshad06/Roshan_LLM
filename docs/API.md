# قرارداد API سندیار

رابط تعاملی Swagger در `/api/docs/` و قرارداد آن در `/api/schema/` ارائه می‌شود. برای اجرای درخواست‌ها، در Swagger روی **Authorize** بزنید و با حساب خود وارد شوید. راهنمای فارسی در `/api/guide/` در دسترس است.

پرسش‌هایی مانند «چند تا از سندها فقط انگلیسی هستند و کدام دوزبانه‌اند؟» در همان حساب و با بررسی متن همهٔ قطعه‌ها محاسبه می‌شوند. این شمارش برای مجموعه‌های فارسی و انگلیسی طراحی شده و بر پایهٔ نوشتار استخراج‌شده تخمین زده می‌شود. برای پرسش محتوایی، هنگام محدودیت درخواست سرویس، سامانه می‌تواند نقل‌قول‌های جست‌وجوی محلی را با برچسب مشخص برگرداند.

پیشوند همهٔ مسیرها `http://localhost:8000/api/` است. شناسه‌ها عددی‌اند و اسلش پایانی هر مسیر لازم است. پاسخ‌ها با JSON و متن UTF-8 بازمی‌گردند. احراز هویت در تمام مسیرهای داده الزامی است.

رابط وب با نشست Django و برای درخواست‌های نوشتنی با کوکی CSRF و هدر `X-CSRFToken` کار می‌کند. در PowerShell، گزینهٔ `-u demo` در curl.exe رمز را در ترمینال می‌پرسد. آدرس HTTP این راهنما برای اجرای محلی روی loopback است. [راهنمای احراز هویت DRF](https://www.django-rest-framework.org/api-guide/authentication/)

## اسناد

| متد و مسیر | ورودی | خروجی موفق |
|---|---|---|
| `GET /documents/` | `search` اختیاری، روی عنوان، نام فایل یا متن کامل | 200، آرایهٔ خلاصهٔ اسناد از تازه‌ترین ویرایش |
| `GET /documents/search/` | پارامتر الزامی `q` از ۱ تا ۳۰۰۰ نویسه | 200، حداکثر چهار قطعه با فیلدهای `document_id, title, location, quote` به ترتیب ارتباط. جست‌وجوی ترکیبی بدون فراخوانی OpenRouter انجام می‌شود. |
| `POST /documents/` | multipart/form-data، فیلد `file` الزامی، `title` اختیاری | 201، جزئیات شامل متن استخراج‌شده |
| `GET /documents/{id}/` | شناسهٔ سند | 200، جزئیات |
| `PATCH /documents/{id}/` | JSON با دست‌کم یکی از `title` یا `text` | 200، جزئیات به‌روز |
| `DELETE /documents/{id}/` | شناسهٔ سند | 204، بدنهٔ خالی |

خلاصه شامل `id, title, filename, created_at, updated_at` است. جزئیات فیلد `text` را هم دارد. عنوان تا ۲۴۰ نویسه و متن ذخیره‌شده تا ۶۰۰٬۰۰۰ نویسه پذیرفته می‌شود. فرمت‌های مجاز `.docx`، `.pdf`، `.xlsx`، `.txt`، `.png`، `.jpg` و `.jpeg` هستند. متن ساده با UTF-8 یا UTF-16 دارای BOM خوانده می‌شود. در تغییر متن، قطعه‌ها و بردارها در یک تراکنش جایگزین می‌شوند. تغییر عنوان به‌تنهایی به محاسبهٔ بردار نیاز ندارد.

~~~powershell
curl.exe -u demo "http://localhost:8000/api/documents/?search=ALF-27"
curl.exe -u demo -F "file=@samples/en/hazm-guide.docx" -F "title=My copy" http://localhost:8000/api/documents/
~~~

برای نمونهٔ زیر، ابتدا یک **کپی آزمایشی** با دستور بالا بسازید. مقدار متغیر را از `id` پاسخ ایجاد بردارید. این دستور ویرایش از فرم معمولی پشتیبانی‌شده در DRF استفاده می‌کند.

~~~powershell
$documentId = Read-Host "ID of the uploaded copy"
curl.exe -u demo -X PATCH -d "title=Updated test copy" "http://localhost:8000/api/documents/$documentId/"
~~~

## گفت‌وگو و پرسش

| متد و مسیر | ورودی | خروجی موفق |
|---|---|---|
| `GET /conversations/` | بدون ورودی | 200، آرایهٔ گفت‌وگوها، جدیدترین در ابتدا |
| `POST /conversations/` | شیء خالی یا بدنهٔ خالی | 201، گفت‌وگو با `id, title, created_at` |
| `GET /conversations/{id}/` | شناسهٔ گفت‌وگو | 200، مشخصات و `turns` به ترتیب زمان |
| `POST /conversations/{id}/ask/` | فیلد متنی `question`، حداکثر ۳۰۰۰ نویسه | 201، نوبت جدید شامل پرسش، پاسخ و منابع |
| `DELETE /conversations/{id}/` | شناسهٔ گفت‌وگو | 204، حذف گفت‌وگو و تمام نوبت‌های آن |

برای پرسش پیگیری همان شناسهٔ گفت‌وگو را نگه دارید. شناسهٔ مالک از نشست یا اطلاعات ورود گرفته می‌شود. کلاینت نیازی به ارسال مالک ندارد.

~~~powershell
$chat = (curl.exe -s -u demo -X POST http://localhost:8000/api/conversations/) | ConvertFrom-Json
curl.exe -u demo --data-urlencode "question=Which inputs does the ALF-27 pilot accept?" "http://localhost:8000/api/conversations/$($chat.id)/ask/"
curl.exe -u demo --data-urlencode "question=What is its upload limit? Reply in Persian." "http://localhost:8000/api/conversations/$($chat.id)/ask/"
curl.exe -u demo "http://localhost:8000/api/conversations/$($chat.id)/"
~~~

نمونهٔ شکل پاسخ با شناسه‌های نمایشی و نقل‌قول موجود در پروندهٔ پایلوت:

~~~json
{
  "id": 7,
  "question": "سقف حجمش چقدر است؟ به انگلیسی جواب بده.",
  "answer": "The upload limit is 24 MB per file. [1]",
  "sources": [
    {
      "document_id": 11,
      "title": "پایلوت الفبا برای بایگانی",
      "location": "Document body",
      "quote": "Its upload limit is 24 MB per file."
    }
  ],
  "created_at": "2026-11-19T10:30:00Z"
}
~~~

بدون شواهد کافی یک نوبت با پیام صریح و آرایهٔ خالی `sources` ثبت می‌شود. در خطای ارتباط یا پاسخ نامعتبر مدل، وضعیت 503 برمی‌گردد و نوبتی ثبت نمی‌شود. منابع تاریخچه تصویری از شاهد در زمان پاسخ‌اند و پس از ویرایش یا حذف سند در تاریخچهٔ همان صاحب باقی می‌مانند.

## خطاها

رابط وب برای لغو ارسال، سؤال را ابتدا به `POST /conversations/{id}/preview/` می‌فرستد. این درخواست با همان فیلد `question` و یک `replace_id` اختیاری برای آخرین نوبت، یک `ticket` امضاشده می‌دهد. در این مرحله هیچ نوبتی ثبت نمی‌شود. کلاینت برای ثبت، پاسخ را به شکل `{"ticket":"…"}` به `POST /conversations/{id}/confirm/` می‌فرستد. مهلت تأیید ده دقیقه است. اگر تاریخچه در این فاصله تغییر کند، سرور ۴۰۹ می‌دهد. مسیر `ask/` همچنان با یک درخواست کار می‌کند.

برای بارگذاری چند فایل، رابط وب هر فایل انتخابی را با یک درخواست مستقل به مسیر بارگذاری می‌فرستد. اگر فایلی پردازش نشود، نام و خطای همان فایل نمایش داده می‌شود و کاربر می‌تواند فقط فایل‌های ناموفق را دوباره بفرستد.

| وضعیت | معنی |
|---|---|
| 400 | ورودی ناقص، متن یا فایل نامعتبر یا عبور از محدودیت پردازش |
| 401 | احراز هویت انجام نشده یا اطلاعات ورود نامعتبر است |
| 403 | از جمله درخواست تغییر با نشست بدون CSRF معتبر |
| 404 | شیء وجود ندارد یا متعلق به این حساب نیست |
| 409 | تغییر هم‌زمان سند، جلسه یا شاهد؛ داده را دوباره بخوانید و درخواست را تکرار کنید |
| 503 | کلید، مدل بازیابی یا سرویس مدل زبانی در دسترس نیست، یا مدل خروجی قابل استناد نداد |

خطاهای عمومی یک `detail` متنی دارند. خطای اعتبارسنجی DRF به‌صورت نگاشت نام فیلد به فهرست پیام‌ها برمی‌گردد.


### انتخاب مدل گفت‌وگو

`GET /api/models/` فهرست مدل‌های قابل انتخاب را برمی‌گرداند. هنگام ایجاد گفت‌وگو با `POST /api/conversations/` می‌توانید شناسهٔ مدل را در `language_model` بفرستید. برای تغییر آن از `PATCH /api/conversations/{id}/` با بدنهٔ `{"language_model": 2}` استفاده کنید. مقدار `null` انتخاب خودکار را فعال می‌کند. مدیریت فهرست مدل‌ها از پنل Django Admin انجام می‌شود.
`GET /api/documents/graph/` returns owned document nodes and undirected edges with a reason and two cited passages.

`PUT /api/conversations/{id}/turns/{turn_id}/rating/` accepts `{"rating": 1}` for a like, `-1` for a dislike and `0` to clear. The conversation owner can replace their vote. The current rating is included with each turn.
