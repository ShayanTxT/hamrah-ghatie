# معماری فنی / Architecture

> خلاصهای برای کسانی که میخواهند کد را بخوانند یا تغییر دهند.
> نسخهٔ کامل فارسی: [README.fa.md](../README.fa.md) · انگلیسی:
> [README.en.md](../README.en.md)

## اصل اول: جدایی هسته از رابط

```
┌──────────────────────────────────────────────────────────────┐
│  hamrah/ui  (PySide6 — فقط نمایش)                             │
│  MainWindow · Dashboard · Readiness · Library · Chat · LAN    │
│  workers.py (QThread + Signal)                                │
└───────────────────────────┬──────────────────────────────────┘
                            │ Signal / callback (بدون منطق)
┌───────────────────────────▼──────────────────────────────────┐
│  hamrah/core  (پایتون خالص، بدون Qt، قابل تست)                │
│  probes · netcheck · downloader · pagesaver · checklist       │
│  library · zim_reader · textutil · persian · llama · sysinfo  │
│  lan/{crypto,protocol,discovery,node}                        │
│  db · config · paths · http · netpolicy · errors · jalali     │
└───────────────────────────┬──────────────────────────────────┘
                            │
              ┌─────────────▼──────────────┐
              │  data/  (همهچیز کنار exe)  │
              │  app.db (SQLite + FTS5)    │
              │  settings.json / *.json    │
              │  models/ zim/ downloads/   │
              │  logs/ incoming/ pages/    │
              └────────────────────────────┘
```

هیچ ماژولی در `hamrah/core` نباید `PySide6` را import کند. تستها نیز به Qt
نیاز ندارند؛ بنابراین CI بدون نصب کتابخانههای گرافیکی سیستمی هم سبز میشود.

## سیاست شبکه (`netpolicy.py`)

تمام درخواستها از `HttpClient.open()` عبور میکنند و `NetworkGuard` هدف آنها
را ثبت/بررسی میکند. تنها اهداف مجاز:

| Purpose | مقصد |
|---|---|
| `PROBE` | سایتهای داخلی/خارجی، DNS، مودم |
| `DOWNLOAD` / `PAGE_ASSET` | فقط فایلهایی که کاربر شروع کرده |
| `LOCAL_AI` | **فقط** `127.0.0.1` / `localhost` (هر مقصد دیگر مسدود) |
| `LAN` | UDP broadcast و TCP همان subnet |

تست `test_network_policy.py` سورسکد را برای `requests`, `httpx`, CDN،
آنالیتیکس و آپدیت خودکار اسکن میکند.

## تشخیص وضعیت (مرحلهٔ ۱)

`probes.py` تستها را در `ThreadPoolExecutor` اجرا میکند (هر کدام timeout
مستقل، کل چرخه حدود ۲ ثانیه). `netcheck.classify()` نتیجه را به یکی از
`FREE / NATIONAL / DOWN` تبدیل میکند و `StateTracker` با هیسترزیس (۲ نمونهٔ
پیاپی) جلوی نوسان را میگیرد. رویدادها، نمونهها و دورههای قطعی در SQLite
ذخیره میشوند؛ `timeline()` دادهٔ نمودار ۲۴ ساعت را آماده میکند.

## جستجوی فارسی (مرحلهٔ ۳)

`persian.normalize()`: NFKC → یکسانسازی `ی/ي`, `ک/ك`, همزهها، حذف اعراب و
کشیده، تبدیل نیمفاصله به فاصله، یکسانسازی ارقام. `fts_index_text()` علاوه
بر متن نرمال، توکنهای چسبیدهٔ دوتایی اضافه میکند تا «میروم» و «می‌روم»
همدیگر را پیدا کنند. `build_fts_query()` یک عبارت FTS5 امن با جستجوی
پیشوندی و شاخهٔ OR برای حالت چسبیده میسازد. ایندکس در `documents_fts`
(FTS5, `unicode61 remove_diacritics 2`) ذخیره میشود.

## خواندن ZIM (مرحلهٔ ۳)

`zim_reader.py` یک پیادهسازی خالص پایتون از فرمت ZIM است: هدر ۸۰ بایتی،
لیست MIME، اشارهگرهای مسیر/عنوان/کلاستر، direntها (content / redirect)،
و کلاسترهای بدون فشردهسازی / zlib / bzip2 / LZMA2(XZ) / Zstandard (با
پشتیبانی از آفست ۸ بایتی در نسخهٔ ۶). در صورت برخورد با فرمت ناشناخته،
در صورت نصب بودن بستهٔ اختیاری `libzim` از آن بهعنوان پشتیبان استفاده
میشود.

## صف دانلود (مرحلهٔ ۲)

فایل همیشه `*.part` است. قبل از ادامه، `ETag`/`Last-Modified` بهصورت
`If-Range` و `Range: bytes=N-` فرستاده میشود. پاسخ `206` ادامه میدهد؛
پاسخ `200` یعنی سرور Range را نادیده گرفته و فایل امنانه از نو نوشته
میشود. `DownloadQueue.run_loop()` در `QThread` اجرا میشود و هنگام
`national`/`down` متوقف میگردد.

## مدل محلی (مرحلهٔ ۴)

`llama.py` فرایند `llama-server.exe` را با `-m model.gguf --host 127.0.0.1
--port 18081 -c 4096 -ngl N -t T` اجرا میکند، منتظر `/health` میماند و سپس
درخواست `POST /completion` با `stream: true` میفرستد. خطوط SSE
(`data: {...}`) کلمهبهکلمه به UI پاس داده میشوند. `sysinfo.recommend()`
بر اساس رم و VRAM یکی از پروفایلهای 3B / 7B / 14B را پیشنهاد میدهد.

## شبکهٔ محلی (مرحلهٔ ۵)

1. `discovery.py`: UDP broadcast با HMAC(کد جفتسازی) + برچسب زمانی.
2. `crypto.py`: سلام دوطرفه با اثبات HMAC، تبادل کلید موقتی X25519،
   `HKDF-SHA256(ECDH || PSK)` → دو کلید جهتدار، قابهای AES-256-GCM
   (هدر + بلاب جداگانه، nonce شمارندهای). کلید ثابت دستگاه در
   `data/peers.json` پین میشود.
3. `node.py`: TCP سرور/کلاینت، چت، پیشنهاد فایل ← **تأیید کاربر** ←
   `*.part` با آفست فعلی → چانکهای ۲۵۶ کیلوبایتی → بررسی SHA-256 →
   rename. شناسهٔ فایل پایدار است، پس قطع ارتباط دوباره همان فایل را ادامه
   میدهد.

> ⚠️ این پروتکل حسابرسی نشده؛ جزئیات در [SECURITY.md](../SECURITY.md).

## بستهبندی

`hamrah-ghatie.spec` (PyInstaller onedir) منابع `assets/` و وابستگیها را
جمع میکند. `Paths` در حالت frozen پوشهٔ `data` را کنار `sys.executable`
میسازد و منابع را از `sys._MEIPASS` میخواند؛ بنابراین کپی کردن پوشه =
انتقال کامل برنامه.
