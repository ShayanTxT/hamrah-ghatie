# چکلیست آمادهسازی ریپو روی گیتهاب

> مالک: **ShayanTxT** (لقب: `shayan.txt`) · آدرس: <https://github.com/ShayanTxT>
> نام پیشنهادی ریپو: **`hamrah-ghatie`**
> تمام لینکها و بجهای داخل READMEها از قبل روی
> `https://github.com/ShayanTxT/hamrah-ghatie` تنظیم شدهاند.

---

## ۱. ساخت ریپو

1. برو به <https://github.com/new>
2. **Repository name:** `hamrah-ghatie`
3. **Description** (کپی کن):
   ```
   همراه قطعی — برنامهٔ ویندوزی آفلاین برای زمان قطعی اینترنت ایران؛ وضعیت اتصال، کیف آمادگی، ویکیپدیای ZIM، مدل GGUF محلی و شبکهٔ محلی رمزنگاریشده. | Offline-first Windows companion for internet blackouts.
   ```
4. **Public** ✅ (اگر خصوصی خواستی، بجها و لینکها همچنان کار میکنند).
5. ✅ Add a README file → **نزن** (ما README داریم؛ بعدش پوش میکنیم).
6. ✅ Add `.gitignore` → **نزن** (فایل خودمان موجود است).
7. ✅ Choose a license → **نزن** (فایل `LICENSE` ما MIT است).
8. Create repository.

---

## ۲. پوش کردن کد (از همان پوشهٔ پروژه)

### راحتترین راه — اسکریپت آماده

```bat
tools\publish.bat
```

یا روی لینوکس/مک:

```bash
bash tools/publish.sh
```

این اسکریپت `git init`، تنظیم `origin`، کامیت اولیه و `git push -u origin main`
را انجام میدهد.

### دستی

```bash
cd hamrah-ghatie
git init
git remote add origin https://github.com/ShayanTxT/hamrah-ghatie.git
git add .
git commit -m "feat: initial release of Hamrah Ghatie v1.0.0"
git branch -M main
git push -u origin main
```

> اگر از قبل ریپو ساختهای و `README` خالی توش هست:
> `git pull origin main --rebase` بزن بعد پوش کن.

### بررسی قبل از پوش

```bash
git status --short
# نباید data/، *.db، *.log، *.gguf، *.part، *.exe، *.zip دیده شوند
du -sh .        # حدود ۱۶ مگابایت (شامل ZIM نمونهٔ ۱۴ مگابایتی)
pytest -q       # ۵۵ تست سبز
```

---

## ۳. تنظیمات ریپو (Settings → General)

| بخش | مقدار |
|---|---|
| **Website** | `https://github.com/ShayanTxT/hamrah-ghatie#readme` |
| **Topics** | `offline-first`, `persian`, `farsi`, `rtl`, `windows`, `pyside6`, `python`, `internet-blackout`, `iran`, `kiwix`, `zim`, `llama-cpp`, `gguf`, `local-llm`, `sqlite-fts5`, `lan`, `portable`, `solar-calendar` |
| **Social preview** | آپلود کن: `.github/assets/social-preview.png` (۱۲۸۰×۶۴۰) |
| **Features → Issues** | ✅ روشن |
| **Features → Discussions** | ✅ روشن (برای سؤالها) |
| **Features → Projects** | ✅ اختیاری |
| **Features → Wiki** | ❌ خاموش (مستندات تو `docs/` است) |
| **Pull Requests** | ✅ Allow squash merging (پیشفرض = squash) |
| **Danger Zone** | هیچکدام را نزن! |

### Security (Settings → Code security)

- ✅ **Private vulnerability reporting** روشن (چون `SECURITY.md` داریم).
- ✅ **Dependabot alerts** و **Dependabot security updates** روشن
  (`dependabot.yml` هم وابستگیها را هفتگی بهروز میکند).
- ✅ Secret scanning (برای ریپوهای public رایگان است).

### Actions (Settings → Actions → General)

- **Workflow permissions:** `Read and write permissions` (برای ساخت Release لازم است).
- ✅ Allow GitHub Actions to create and approve pull requests → اختیاری.

---

## ۴. برچسبها (Issues → Labels)

بجهای پیشفرض `bug`, `enhancement`, `documentation`, `good first issue`,
`help wanted` وجود دارند. اضافه کن:

| نام | رنگ پیشنهادی | توضیح |
|---|---|---|
| `offline` | `#0f9d58` | مربوط به تضمین آفلاین بودن |
| `network` | `#2f6fed` | تست اتصال / دانلود / LAN |
| `ui` | `#8e44ad` | رابط کاربری و تم |
| `zim` | `#e9962f` | خواننده و ایندکس ZIM |
| `ai` | `#00a0a0` | مدل محلی / llama.cpp |
| `packaging` | `#6b7280` | PyInstaller / build.bat |
| `automated` | `#ededed` | ساخت Dependabot |
| `wontfix` | `#ffffff` | خارج از scope |

---

## ۵. گرفتن فایل exe پرتابل

**روش الف — GitHub Actions (پیشنهادی):**

1. برو به `Actions` → workflow **Build Windows portable** → `Run workflow`.
2. گزینهٔ `with_libzim` رو `false` بذار (پیشفرض؛ چون GPLv3 و ۲۱ مگ اضافه).
3. بعد از اتمام، از `Artifacts` فایل
   `hamrah-ghatie-portable-windows-x64.zip` رو بگیر. همراهش
   `SHA256SUMS.txt` هم هست.

**روش ب — ساخت لوکال روی ویندوز:**

```bat
build.bat
:: خروجی: dist\همراه قطعی\HamrahGhatie.exe
::        dist\همراه_قطعی_پرتابل.zip
```

**روش ج — ساخت Release با تگ (اتوماتیک):**

```bash
git tag -a v1.0.0 -m "همراه قطعی ۱٫۰٫۰"
git push origin v1.0.0
```

 workflow روی ویندوز میسازد و همان ZIP را به **Releases** صفحهٔ
`v1.0.0` ضمیمه میکند (با `CHANGELOG.md` بهعنوان توضیحات).

---

## ۶. بجها و لینکها (اگر اسم ریپو را عوض کردی)

همهٔ بجها به `ShayanTxT/hamrah-ghatie` اشاره دارند. اگر اسم دیگری
انتخاب کردی، این دستور را بزن:

```bash
grep -rl "ShayanTxT/hamrah-ghatie" . --exclude-dir=.git | xargs sed -i 's/ShayanTxT\/hamrah-ghatie/ShayanTxT\/NEW_NAME/g'
```

فایلهایی که لینک دارند: `README.md`, `README.fa.md`, `README.en.md`,
`pyproject.toml`, `CONTRIBUTING.md`, `SUPPORT.md`, `SECURITY.md`,
`.github/ISSUE_TEMPLATE/*.yml`, `.github/REPO_SETUP.md`.

---

## ۷. محتوای قابل حذف (اگر خواستی ریپو سبکتر شود)

| مسیر | حجم | توضیح |
|---|---:|---|
| `samples/wikipedia_climate_change_mini.zim` | ۱۴ مگ | فقط برای تست سریع ZIM؛ قابل حذف (تستها `skip` میشوند). |
| `docs/screenshots/*.png` | ۵۵۰ کیلوبایت | اسکرینشات README؛ قابل حذف. |
| `.github/assets/*.png` | ۱۶۵ کیلوبایت | بنر و سوشال پرویو؛ نگهداشتنش بهتر است. |

بدون اینها ریپو حدود **۱ مگابایت** میشود.

---

## ۸. چکلیست نهایی ✅

- [ ] ریپو `hamrah-ghatie` ساخته شد و `main` پوش شد.
- [ ] Actions سبز شد (`CI` روی اوبونتو + ویندوز).
- [ ] توضیحات، topics و social preview تنظیم شد.
- [ ] Discussions و Private vulnerability reporting روشن شد.
- [ ] workflow ساخت ویندوزی اجرا شد و ZIP دانلود شد.
- [ ] تگ `v1.0.0` زده شد و Release ساخته شد.
- [ ] یه stars ⭐ بده به ریپو خودت 😄

هیچ **Secret**ای لازم نیست؛ همهچیز با `GITHUB_TOKEN` خودکار کار میکند.
