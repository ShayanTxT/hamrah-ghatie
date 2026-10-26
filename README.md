<div align="center">
  <img src=".github/assets/banner.png" alt="همراه قطعی — Hamrah Ghatie" width="100%">
</div>

<div align="center">

[![CI](https://github.com/ShayanTxT/hamrah-ghatie/actions/workflows/ci.yml/badge.svg)](https://github.com/ShayanTxT/hamrah-ghatie/actions/workflows/ci.yml)
[![Build Windows portable](https://github.com/ShayanTxT/hamrah-ghatie/actions/workflows/build-windows.yml/badge.svg)](https://github.com/ShayanTxT/hamrah-ghatie/actions/workflows/build-windows.yml)
[![Release](https://img.shields.io/github/v/release/ShayanTxT/hamrah-ghatie?display_name=tag)](https://github.com/ShayanTxT/hamrah-ghatie/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Windows 10/11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![100% offline](https://img.shields.io/badge/100%25-offline-2ea043)](https://github.com/ShayanTxT/hamrah-ghatie#readme)

# همراه قطعی · Hamrah Ghatie

**برنامهای پرتابل و ۱۰۰٪ آفلاین برای روزهای قطعی اینترنت ایران.**
**A portable, 100% offline Windows companion for internet blackouts.**

<br>

| 📖 مستندات کامل / Full docs | |
|:---:|:---:|
| **[🇮🇷 README به فارسی](README.fa.md)** | **[🇬🇧 README in English](README.en.md)** |

</div>

---

## چیست؟ / What is it?

وقتی اینترنت جهانی قطع میشود — یا فقط «اینترنت ملی» میماند، یا هیچچیز نمیماند —
این برنامه همچنان کار میکند. بعد از **یکبار آمادهسازی** (وقتی نت دارید)،
هیچ CDN، API ابری، فونت آنلاین، تلهٔمتری یا بررسی آپدیتی وجود ندارد.

When the global internet is cut — or only a national intranet remains, or
nothing at all — this app keeps working. After a **one-time preparation**,
there is no CDN, cloud API, web font, telemetry or auto-update check.

| | فارسی | English |
|---|---|---|
| 🟢🟡🔴 | **داشبورد وضعیت اتصال** — تست داخلی/خارجی/DNS/مودم، تاریخچهٔ قطعیها، نمودار ۲۴ ساعته و اعلان ویژه هنگام برگشتن نت | **Connectivity dashboard** — internal/external/DNS/router probes, outage history, 24h chart, special alert when the internet returns |
| 🎒 | **کیف آمادگی** — صف دانلود قابلادامه، ذخیرهٔ کامل صفحات وب، چکلیست ۱۸ قلمی | **Readiness kit** — resumable downloads, full web-page capture, 18-item checklist |
| 📚 | **کتابخانهٔ آفلاین** — ZIM ویکیپدیا + PDF/HTML/TXT با جستجوی تماممتن فارسی | **Offline library** — Wikipedia ZIM + PDF/HTML/TXT with Persian full-text search |
| 🤖 | **دستیار آفلاین** — مدل GGUF محلی با llama.cpp، پاسخ استریم و تاریخچه | **Offline AI** — local GGUF via llama.cpp, streamed answers, saved history |
| 🖧 | **شبکهٔ محلی** — کشف خودکار، چت و فایل رمزنگاریشده بدون اینترنت | **LAN sharing** — auto-discovery, encrypted chat & file transfer, no internet |

**ویژگیها:** ویندوز ۱۰/۱۱ ۶۴بیت · بدون نصب (از روی فلش) · رابط کاملاً فارسی و
راستبهچپ · تقویم شمسی · فونت وزیرمتن داخل بسته · حالت روشن و تیره · تاریخچه و
دادهها همگی در پوشهٔ `data` کنار exe.

**Features:** Windows 10/11 x64 · portable (runs from USB) · full Persian RTL
UI · Solar calendar · bundled Vazirmatn font · light & dark themes · all data
in `data/` next to the exe.

---

## 📸 نمایی از برنامه / Screenshots

<div align="center">
  <img src="docs/screenshots/01-dashboard.png" alt="داشبورد وضعیت اتصال" width="46%">
  <img src="docs/screenshots/03-library.png" alt="کتابخانهٔ آفلاین" width="46%">
</div>

<div align="center">
  <img src="docs/screenshots/04-assistant.png" alt="دستیار آفلاین" width="46%">
  <img src="docs/screenshots/01-dashboard-dark.png" alt="حالت تیره" width="46%">
</div>

همهٔ اسکرینشاتها در [`docs/screenshots/`](docs/screenshots/) موجودند.

---

## 🚀 شروع سریع / Quick start

### ۱) گرفتن برنامه / Get the app

| روش / Method | دستور / Command |
|---|---|
| دانلود نسخهٔ آماده / Prebuilt | [Releases](https://github.com/ShayanTxT/hamrah-ghatie/releases) → `hamrah-ghatie-portable-win-x64.zip` |
| ساخت خودت / Build yourself | `build.bat` (روی ویندوز / on Windows) |
| ساخت با CI / Build via CI | `Actions → Build Windows portable → Run workflow` |
| اجرا از سورس / Run from source | `pip install -r requirements.txt` → `python run.py --demo --stage 1` |

> ⚠️ **صداقت / Honesty:** محیط توسعه لینوکس بوده؛ بستهبندی PyInstaller و ۵۵
> تست و رابط کاربری اینجا واقعاً اجرا شدهاند، ولی **فایل exe ویندوزی باید
> روی ویندوز ساخته شود** (`build.bat` یا workflow). جزئیات کامل در
> [README.fa.md](README.fa.md) / [README.en.md](README.en.md).

### ۲) قبل از قطعی دانلود کن / Download before the blackout

```bat
python tools\prepare_downloads.py --list
python tools\prepare_downloads.py --minimal
```

بستهٔ حداقلی ≈ **۷٫۶ گیگ**: مدل `Qwen2.5-7B-Instruct Q4_K_M` (۴٫۷ گیگ) +
`wikipedia_fa_all_mini` (۲٫۶ گیگ) + `llama-server.exe` نسخهٔ CUDA.
همهچیز قابل وارد کردن از فلش است: `python tools\prepare_downloads.py --import-folder D:\`.

Minimal kit ≈ **7.6 GB**: `Qwen2.5-7B-Instruct Q4_K_M` (4.7 GB) +
`wikipedia_fa_all_mini` (2.6 GB) + CUDA `llama-server.exe`. Everything can be
imported from a USB stick.

### ۳) تست مرحلهبهمرحله / Test stage by stage

```bat
HamrahGhatie.exe --demo --stage 1   :: شبیهسازی قطعی بدون هیچ درخواست شبکهای
HamrahGhatie.exe --stage 5          :: همهٔ امکانات
```

`--demo` چرخهٔ «آزاد ← فقط ملی ← قطع کامل ← برگشت» را بدون اینترنت شبیهسازی
میکند تا اعلانها و تاریخچه را ببینید.

---

## 🔒 تضمین آفلاین / Offline guarantee

تنها درخواستهای شبکهای مجاز: **تست اتصال**، **دانلودهایی که خودتان شروع
میکنید**، **ارتباط loopback با مدل محلی** و **شبکهٔ محلی**. تستها سورسکد را
برای CDN/تلهٔمتری/آپدیت خودکار اسکن میکنند.

Only four kinds of network traffic are allowed: **connectivity probes**,
**user-initiated downloads**, **loopback to the local LLM**, and **LAN
traffic**. Automated tests scan the source for CDNs/telemetry/auto-updates.

جزئیات: [`hamrah/core/netpolicy.py`](hamrah/core/netpolicy.py) ·
[معماری / Architecture](docs/ARCHITECTURE.md)

---

## 📚 مستندات / Documentation

| فارسی | English |
|---|---|
| [راهنمای کامل فارسی](README.fa.md) | [Full English README](README.en.md) |
| [معماری فنی](docs/ARCHITECTURE.md) | [Architecture (EN)](docs/ARCHITECTURE.md) |
| [عیبیابی](README.fa.md#troubleshooting) | [Troubleshooting](README.en.md#troubleshooting) |
| [راهنمای مشارکت](CONTRIBUTING.md) | [Contributing](CONTRIBUTING.md) |
| [امنیت](SECURITY.md) | [Security](SECURITY.md) |
| [پشتیبانی](SUPPORT.md) | [Support](SUPPORT.md) |
| [تغییرات](CHANGELOG.md) | [Changelog](CHANGELOG.md) |
| [مجوزها](LICENSE-THIRD-PARTY.md) | [Third-party licenses](LICENSE-THIRD-PARTY.md) |
| [تنظیم ریپو روی گیتهاب](.github/REPO_SETUP.md) | [GitHub repo setup](.github/REPO_SETUP.md) |

---

## 🧪 وضعیت تست / Test status

- ✅ **۵۵ تست pytest سبز** (منطق، جستجو، دانلود، ZIM، رمزنگاری LAN، سیاست شبکه)
- ✅ خواندن **ZIM واقعی** (۱۴ مگ، ۲۰٬۵۶۵ ورودی) و انتقال **فایل واقعی** بین دو گره TCP
- ✅ رابط PySide6 بهصورت offscreen برای `--stage 1..5` + حالت تیره/روشن
- ✅ ساخت و اجرای **بستهٔ frozen PyInstaller** (لینوکس، ۲۵۱ مگابایت)
- ⚠️ تستنشده: exe ویندوزی، اعلان سینی ویندوز، مدل GGUF واقعی روی GPU

---

<div align="center">

ساختهشده توسط [**ShayanTxT**](https://github.com/ShayanTxT) (لقب `shayan.txt`)
· مجوز [MIT](LICENSE) · اگر مفید بود ⭐ بدهید!

Made by [**ShayanTxT**](https://github.com/ShayanTxT) · [MIT](LICENSE) · star ⭐ if useful.

</div>
