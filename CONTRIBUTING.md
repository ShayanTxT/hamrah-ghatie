# مشارکت در همراه قطعی / Contributing

فارسی | [English](#english)

## فارسی

ممنون که میخوای کمک کنی! این پروژه شخصی و آفلاینمحور است؛ لطفاً قبل از هر
تغییری، «قانون طلایی» را بخوان: **برنامه بعد از راهاندازی اول نباید هیچ
درخواست شبکهای جز تست اتصال، دانلودهای شروعشده توسط کاربر، ارتباط loopback
با مدل محلی و شبکهٔ محلی داشته باشد.**

### راهاندازی محیط توسعه

```bat
git clone https://github.com/ShayanTxT/hamrah-ghatie.git
cd hamrah-ghatie
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pytest
python run.py --demo --stage 1
```

روی لینوکس/مک: `python3 -m venv .venv` → `pip install -r requirements.txt`
→ `QT_QPA_PLATFORM=offscreen python3 run.py --demo`. ممکن است به کتابخانهٔ
سیستمی `libxkbcommon0` نیاز داشته باشید.

### اجرای تستها

```bash
pytest -q
```

همهٔ تستها باید بدون اینترنت و بدون باز کردن سوکت real (جز سرورهای محلی
loopback داخل خود تستها) اجرا شوند. تستها نباید به PySide6 وابسته باشند.

### اصول کدنویسی

- **هسته مستقل است:** ماژولهای `hamrah/core` نباید `PySide6` را import کنند.
  رابط کاربری فقط در `hamrah/ui` است و با `Signal` با هسته حرف میزند.
- **خطاها فارسی و کاربرپسند:** از `hamrah/core/errors.py` و
  `log_exception()` استفاده کن؛ متن فنی انگلیسی فقط در `data/logs/app.log`.
- **سیاست شبکه:** هر درخواست HTTP/socket باید از `NetworkGuard` با یکی از
  اهداف `PROBE`, `DOWNLOAD`, `PAGE_ASSET`, `LOCAL_AI`, `LAN` عبور کند. اضافه
  کردن CDN، تلهٔمتری، آپدیتخودکار یا فونت آنلاین ممنوع است (تست
  `test_network_policy.py` جلویش را میگیرد).
- **سازگاری:** کد باید روی Python 3.11 (ویندوز ۱۰/۱۱ x64) اجرا شود. از
  ویژگیهای 3.12+ استفاده نکن.
- **سبک:** ۴ فاصله برای توارفتگی پایتون، حداکثر طول خط حدود ۱۰۰ کاراکتر،
  نام متغیرهای انگلیسی و متنهای قابل نمایش فارسی. `from __future__ import annotations`.
- **تست برای منطق:** هر تغییری در تشخیص وضعیت، جستجو، صف دانلود، ZIM یا
  رمزنگاری LAN حتماً تست جدید داشته باشد.
- **بدون وابستگی جدید بدون دلیل:** هر کتابخانهای که اضافه میکنی باید
  آفلاین، سبک و قابل بستهبندی با PyInstaller باشد.

### اضافه کردن قابلیت

1. اول یک Issue باز کن (قالب «پیشنهاد قابلیت») تا دربارهٔ ضرورت و تأثیر روی
   آفلاین بودن صحبت کنیم.
2. شاخه بساز: `git checkout -b feat/short-name` یا `fix/short-name`.
3. کد + تست + بهروزرسانی `CHANGELOG.md` بنویس.
4. اگر رابط کاربری تغییر کرد، `README.fa.md` و `README.en.md` و در صورت نیاز
   اسکرینشاتها (`python tools/make_screenshots.py`) را بهروز کن.
5. `pytest -q` و حداقل یکبار `python run.py --demo --stage 5` را اجرا کن.
6. PR بده و چکلیست داخل قالب PR را تیک بزن.

### پیام کامیت

از Conventional Commits استفاده میکنیم:
`feat: ...`, `fix: ...`, `docs: ...`, `test: ...`, `refactor: ...`, `build: ...`.

### برچسبها

`bug`, `enhancement`, `offline`, `network`, `ui`, `docs`, `good first issue`,
`help wanted`, `wontfix`.

رفتار همهٔ مشارکتکنندگان تابع [آییننامهٔ رفتاری](CODE_OF_CONDUCT.md) است.

---

<a id="english"></a>
## English

Thanks for contributing! This is an offline-first personal project. The golden
rule: **after first setup the app must make no network requests other than
connectivity probes, user-initiated downloads, loopback traffic to the local
LLM server, and LAN traffic.**

### Development setup

```bash
git clone https://github.com/ShayanTxT/hamrah-ghatie.git
cd hamrah-ghatie
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt pytest
python run.py --demo --stage 1
```

Run tests with `pytest -q`. They must not require internet access or PySide6.

### Code rules

- `hamrah/core` must never import PySide6; only `hamrah/ui` does.
- User-facing errors are Persian and friendly (`errors.py`, `log_exception`);
  technical English goes to `data/logs/app.log`.
- Every HTTP/socket call goes through `NetworkGuard` with one of the allowed
  purposes. No CDN, telemetry, auto-update or web fonts — the policy test
  enforces this.
- Target Python 3.11 on Windows 10/11 x64; avoid 3.12+ syntax.
- Add tests for changes to connectivity detection, search, download queue,
  ZIM reading, or LAN crypto.
- New dependencies must be offline-capable and PyInstaller-friendly.

### Pull requests

Open an issue first, branch as `feat/...` or `fix/...`, update `CHANGELOG.md`
and both READMEs if needed, run `pytest -q`, then open a PR and complete the
checklist. Use Conventional Commits.

All contributors are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
