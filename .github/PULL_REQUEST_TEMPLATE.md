## چی تغییر کرد؟ / What does this PR do?

<!-- فارسی یا انگلیسی، کوتاه و واضح / Persian or English, short and clear -->

## مرحلهٔ مربوطه / Related stage

- [ ] ۱ — داشبورد وضعیت اتصال
- [ ] ۲ — کیف آمادگی
- [ ] ۳ — کتابخانهٔ آفلاین
- [ ] ۴ — دستیار هوش مصنوعی
- [ ] ۵ — شبکهٔ محلی
- [ ] رابط کاربری / UI
- [ ] تستها / Tests
- [ ] مستندات / Docs
- [ ] بستهبندی و CI / Build & CI

## ایشوهای مرتبط / Related issues

مثلاً `Closes #12`

## چطور تست کردم؟ / How was this tested?

<!-- دستور دقیق تست، سیستمعامل، نسخهٔ پایتون / Exact commands, OS, Python version -->

```bash
pytest -q
```

## چکلیست / Checklist

- [ ] `pytest -q` بدون خطا اجرا شد.
- [ ] تست جدید برای منطق تغییرکرده نوشتم (تشخیص وضعیت / جستجو / صف دانلود / ZIM / LAN).
- [ ] `hamrah/core` هیچ importای از PySide6 ندارد.
- [ ] خطاهای جدید فارسی و کاربرپسند هستند و جزئیات فنی در لاگ نوشته میشود.
- [ ] هیچ درخواست شبکهای جدیدی اضافه نکردم (یا هدف مجاز `NetworkGuard` مشخص است).
- [ ] وابستگی جدیدی اضافه نکردم (در غیر این صورت `requirements.txt` و `LICENSE-THIRD-PARTY.md` بهروز شد).
- [ ] `README.fa.md` و `README.en.md` در صورت نیاز بهروز شدند.
- [ ] `CHANGELOG.md` بهروز شد.
- [ ] روی ویندوز ۱۰/۱۱ (یا حداقل offscreen) اجرا شد: `python run.py --demo --stage 5`.
- [ ] اطلاعات خصوصی (کد جفتسازی، کلیدها، فایلهای شخصی) در PR نیست.

## اسکرینشات / Screenshots

<!-- اگر UI تغییر کرده، عکس بچسبانید / If UI changed, attach a screenshot -->

---

با تشکر از مشارکتت 🙏 — لطفاً [CONTRIBUTING.md](../CONTRIBUTING.md) و
[CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) را هم ببینید.
