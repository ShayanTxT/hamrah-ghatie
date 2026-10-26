"""مرحلهٔ ۲ — چکلیست آمادگی (همراه اقلام پیشفرض و اقلام دلخواه کاربر)."""
from __future__ import annotations

from typing import Any

from .db import Database

DEFAULT_ITEMS: list[dict[str, str]] = [
    # سیستمعامل و امنیت
    {"category": "سیستمعامل", "title": "آخرین آپدیت ویندوز ۱۰/۱۱",
     "note": "Windows Update را تا جایی که ممکن است کامل کن و حداقل یکبار Restart کن.",
     "link": "ms-settings:windowsupdate"},
    {"category": "سیستمعامل", "title": "ساخت نقظهٔ بازیابی (Restore Point)",
     "note": "اگر بعداً درایوری خراب نصب شد برگردی.", "link": ""},
    {"category": "سیستمعامل", "title": "کپی از درایورهای شبکه و کارت صدا/گرافیک",
     "note": "پوشهٔ C:\\Windows\\System32\\DriverStore\\FileRepository یا بستهٔ درایور سازنده را نگهدار.",
     "link": ""},
    # برنامهها
    {"category": "نصبکنندهها", "title": "نصبکنندهٔ آفلاین 7-Zip / WinRAR",
     "note": "برای باز کردن فایلهای فشرده بدون اینترنت.", "link": ""},
    {"category": "نصبکنندهها", "title": "نصبکنندهٔ آفلاین Firefox / Chrome",
     "note": "نسخهٔ کامل (offline installer) نه دانلودکنندهٔ کوچک.", "link": ""},
    {"category": "نصبکنندهها", "title": "نصبکنندهٔ VLC و SumatraPDF",
     "note": "پخش ویدیو و خواندن PDF بدون اینترنت.", "link": ""},
    {"category": "نصبکنندهها", "title": "نصبکنندهٔ Kiwix (اختیاری)",
     "note": "برنامهٔ اصلی ما ZIM را مستقیم میخواند؛ Kiwix فقط بهعنوان پشتیبان.", "link": ""},
    # دانش
    {"category": "دانش آفلاین", "title": "ZIM ویکیپدیای فارسی (mini)",
     "note": "حدود ۲٫۵ گیگ؛ شامل متن همهٔ مقالهها، بدون عکسهای سنگین.", "link": "https://download.kiwix.org/zim/wikipedia/"},
    {"category": "دانش آفلاین", "title": "ZIM ویکیپدیای انگلیسی (mini)",
     "note": "حدود ۲ تا ۴ گیگ بسته به نسخه.", "link": "https://download.kiwix.org/zim/wikipedia/"},
    {"category": "دانش آفلاین", "title": "PDF کتابچههای کمکهای اولیه و تعمیرات",
     "note": "هر PDF آموزشی که فکر میکنی لازم میشود را در data/library بریز.", "link": ""},
    {"category": "دانش آفلاین", "title": "نقشهٔ آفلاین (OsmAnd / Organic Maps)",
     "note": "فایل نقشهٔ استان/کشور را جداگانه دانلود کن.", "link": ""},
    # هوش مصنوعی
    {"category": "دستیار آفلاین", "title": "llama-server.exe (بستهٔ ویندوزی llama.cpp)",
     "note": "فایل اجرایی را در data/bin قرار بده. نسخهٔ cpu-x64 یا cuda-x64.", "link": "https://github.com/ggml-org/llama.cpp/releases"},
    {"category": "دستیار آفلاین", "title": "مدل GGUF فارسیبلد (Q4_K_M)",
     "note": "پیشنهادی: Qwen2.5-7B-Instruct Q4_K_M حدود ۴٫۷ گیگ؛ در data/models بریز.",
     "link": "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF"},
    # ارتباطات
    {"category": "ارتباطات", "title": "تعیین کد جفتسازی شبکهٔ محلی",
     "note": "یک کد ۶رقمی انتخاب کن و روی همهٔ کامپیوترها یکی بگذار.", "link": ""},
    {"category": "ارتباطات", "title": "کپی برنامه روی فلش (همراه پوشهٔ data)",
     "note": "با کپی کردن پوشه، همهٔ تنظیمات، تاریخچه و کتابخانه منتقل میشود.", "link": ""},
    {"category": "ارتباطات", "title": "شماره تلفنها و اطلاعات مهم بهصورت کاغذی",
     "note": "اگر برق رفت، نباید وابسته به کامپیوتر باشی.", "link": ""},
    # عمومی
    {"category": "عمومی", "title": "شارژ پاوربانک و کابلها",
     "note": "قطعی اینترنت معمولاً با قطعی برق همراه است.", "link": ""},
    {"category": "عمومی", "title": "کپی پشتیبان از فایلهای مهم روی دو وسیله",
     "note": "یکی فلش، یکی هارد اکسترنال.", "link": ""},
]


class Checklist:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.seed_defaults()

    def seed_defaults(self) -> None:
        """اقلام پیشفرض را فقط یکبار اضافه میکند (حذف کاربر محترم شمرده میشود)."""
        count = self.db.scalar("SELECT COUNT(*) FROM checklist WHERE builtin = 1") or 0
        if count:
            return
        with self.db.transaction() as conn:
            for idx, item in enumerate(DEFAULT_ITEMS):
                conn.execute(
                    "INSERT INTO checklist(title, note, category, link, done, sort, builtin) "
                    "VALUES(?, ?, ?, ?, 0, ?, 1)",
                    (item["title"], item["note"], item["category"], item["link"], idx),
                )

    def items(self) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM checklist ORDER BY done ASC, sort ASC, id ASC"
        )
        return [dict(r) for r in rows]

    def add(self, title: str, *, note: str = "", category: str = "سایر", link: str = "") -> int:
        sort = (self.db.scalar("SELECT COALESCE(MAX(sort), 0) + 1 FROM checklist") or 1)
        return self.db.execute(
            "INSERT INTO checklist(title, note, category, link, done, sort, builtin) VALUES(?, ?, ?, ?, 0, ?, 0)",
            (title.strip(), note.strip(), category.strip() or "سایر", link.strip(), sort),
        )

    def toggle(self, item_id: int, done: bool | None = None) -> None:
        if done is None:
            self.db.execute("UPDATE checklist SET done = 1 - done WHERE id = ?", (item_id,))
        else:
            self.db.execute("UPDATE checklist SET done = ? WHERE id = ?", (int(bool(done)), item_id))

    def update(self, item_id: int, **fields: str) -> None:
        allowed = {"title", "note", "category", "link"}
        for key, value in fields.items():
            if key in allowed:
                self.db.execute(f"UPDATE checklist SET {key} = ? WHERE id = ?", (value, item_id))

    def remove(self, item_id: int) -> None:
        self.db.execute("DELETE FROM checklist WHERE id = ?", (item_id,))

    def progress(self) -> tuple[int, int]:
        total = self.db.scalar("SELECT COUNT(*) FROM checklist") or 0
        done = self.db.scalar("SELECT COUNT(*) FROM checklist WHERE done = 1") or 0
        return int(done), int(total)
