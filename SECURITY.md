# سیاست امنیتی / Security Policy

فارسی | [English](#english)

## فارسی

### نسخههای پشتیبانیشده

| نسخه | پشتیبانی |
|---|---|
| `1.0.x` | ✅ پشتیبانی میشود |
| `< 1.0` | ❌ پیشمنتشر، پشتیبانی نمیشود |

### گزارش آسیبپذیری

لطفاً آسیبپذیریها را **در Issue عمومی مطرح نکنید**. از یکی از راههای زیر
استفاده کنید:

1. **GitHub → Security → Report a vulnerability** (پیشنهادی؛ خصوصی است).
2. پیام خصوصی به نگهدارنده: [@ShayanTxT](https://github.com/ShayanTxT).

حداکثر تا ۷ روز پاسخ اولیه داده میشود. لطفاً شامل کنید: نسخهٔ برنامه،
سیستمعامل، گامهای بازتولید، و تأثیر احتمالی.

### نکات امنیتی مهم و صادقانه

- **بدون تلهٔمتری و بدون آپدیت خودکار:** برنامه هیچ دادههای به بیرون
  نمیفرستد و هیچ آپدیای دانلود نمیکند. سیاست شبکه در
  `hamrah/core/netpolicy.py` توسط تستها کنترل میشود.
- **رمزنگاری شبکهٔ محلی حسابرسی نشده است:** پروتکل X25519 + PSK (کد
  جفتسازی) + AES-256-GCM اختصاصی است و یک پروتکل استاندارد/حسابرسیشده
  نیست. برای شبکهٔ خانگی طراحی شده؛ آن را جایگزین VPN/TLS ندانید. کد
  جفتسازی را محرمانه نگهدارید و پس از اولین اتصال، اثر انگشت دستگاهها را
  بررسی کنید.
- **تأیید دریافت فایل:** قبل از دریافت هر فایل از شبکهٔ محلی حتماً دیالوگ
  تأیید نمایش داده میشود و هش SHA-256 فایل کامل بررسی میگردد.
- **مدل هوش مصنوعی کاملاً محلی است:** فقط به `127.0.0.1` متصل میشود؛
  `NetworkGuard` هر مقصد غیر loopback برای هدف `LOCAL_AI` را مسدود میکند.
- **بدون امضا:** فایل exe ساختهشده امضای دیجیتال ندارد و ویندوز ممکن است
  SmartScreen هشدار دهد. حتماً هش فایل را با نسخهای که خودتان ساختهای
  مقایسه کنید.
- **دادههای حساس:** تمام تنظیمات، کلیدهای دستگاه، تاریخچه و کتابخانه در
  پوشهٔ `data/` بهصورت متن ساده/SQLite ذخیره میشوند. اگر کامپیوترتان را با
  دیگران shared میکنید، از رمزگذاری دیسک (BitLocker) استفاده کنید.

---

<a id="english"></a>
## English

### Supported versions

| Version | Supported |
|---|---|
| `1.0.x` | ✅ Yes |
| `< 1.0` | ❌ Pre-release, no |

### Reporting a vulnerability

Please **do not open a public issue**. Use **GitHub → Security → Report a
vulnerability** or contact [@ShayanTxT](https://github.com/ShayanTxT)
privately. Expect an initial response within 7 days. Include version, OS,
reproduction steps and impact.

### Honest security notes

- **No telemetry, no auto-update.** Network policy is enforced by tests in
  `hamrah/core/netpolicy.py`.
- **LAN encryption is unaudited.** It is a custom X25519 + PSK (pairing code)
  + AES-256-GCM scheme, not a standardized/audited protocol. Treat it as
  suitable for a trusted home LAN, not as a VPN/TLS replacement. Keep the
  pairing code secret and verify device fingerprints.
- **Incoming files require explicit approval** and are verified with SHA-256.
- **The local LLM only talks to `127.0.0.1`;** non-loopback destinations are
  blocked by `NetworkGuard`.
- **Builds are unsigned** (SmartScreen may warn). Compare hashes with a build
  you produced yourself.
- **Data at rest is not encrypted.** Settings, identity keys, history and the
  library live in `data/` as JSON/SQLite. Use full-disk encryption on shared
  machines.
