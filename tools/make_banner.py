"""ساخت بنر و تصویر سوشالپرویو گیتهاب — کاملاً آفلاین، فقط Pillow.

اجرا:
    pip install pillow
    python tools/make_banner.py

خروجی:
    .github/assets/banner.png          (۱۲۸۰×۴۲۰، بالای README)
    .github/assets/social-preview.png  (۱۲۸۰×۶۴۰، تنظیمات Social preview گیتهاب)

فونت فارسی از همان فایل باندلشدهٔ برنامه خوانده میشود (وزیرمتن، OFL).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets" / "fonts"
OUT = ROOT / ".github" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

BG_TOP = (13, 20, 34)
BG_BOTTOM = (22, 34, 56)
GREEN = (63, 220, 132)
YELLOW = (255, 200, 87)
RED = (255, 107, 107)
TEXT = (235, 241, 252)
MUTED = (148, 163, 190)
ACCENT = (91, 140, 255)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "Vazirmatn-Bold.ttf" if bold else "Vazirmatn-Regular.ttf"
    return ImageFont.truetype(str(FONTS / name), size, layout_engine=ImageFont.Layout.RAQM)


def gradient(width: int, height: int) -> Image.Image:
    img = Image.new("RGB", (width, height), BG_TOP)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)
    return img


def glow(img: Image.Image, center: tuple[int, int], radius: int, color: tuple[int, int, int], alpha: int) -> None:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = center
    d.ellipse([x - radius, y - radius, x + radius, y + radius], fill=(*color, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(radius // 2))
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"))


def grid(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    for x in range(0, width, 64):
        draw.line([(x, 0), (x, height)], fill=(35, 48, 72), width=1)
    for y in range(0, height, 64):
        draw.line([(0, y), (width, y)], fill=(35, 48, 72), width=1)


def rtext(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
          fnt: ImageFont.FreeTypeFont, fill: tuple[int, int, int]) -> None:
    """متن راستبهچپ فارسی (Raqm شکلدهی و جهت را انجام میدهد)."""
    draw.text(xy, text, font=fnt, fill=fill, direction="rtl", anchor="ra")


def status_column(draw: ImageDraw.ImageDraw, x: int, top: int, scale: float) -> None:
    items = [
        (GREEN, "اینترنت آزاد", "OPEN INTERNET"),
        (YELLOW, "فقط اینترنت ملی", "NATIONAL ONLY"),
        (RED, "قطع کامل", "FULL OUTAGE"),
    ]
    labels = font(int(25 * scale)), font(int(16 * scale))
    for i, (color, fa, en) in enumerate(items):
        y = top + int(i * 92 * scale)
        r = int(9 * scale)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
        draw.text((x + int(28 * scale), y - int(16 * scale)), fa, font=labels[0], fill=TEXT)
        draw.text((x + int(28 * scale), y + int(18 * scale)), en, font=labels[1], fill=MUTED)


def build(width: int, height: int, filename: str) -> Path:
    scale = height / 420.0
    img = gradient(width, height)
    glow(img, (int(1080 * scale), int(120 * scale)), int(230 * scale), ACCENT, 55)
    glow(img, (int(240 * scale), int(330 * scale)), int(190 * scale), GREEN, 30)
    draw = ImageDraw.Draw(img)
    grid(draw, width, height)

    # نوار رنگی بالا
    for i, color in enumerate((GREEN, YELLOW, RED)):
        x0 = int(width * i / 3)
        x1 = int(width * (i + 1) / 3)
        draw.rectangle([x0, 0, x1, int(8 * scale)], fill=color)

    # ستون وضعیتها (سمت چپ)
    status_column(draw, int(90 * scale), int(150 * scale), scale)

    # خط جداکننده
    sep = int(width * 0.46)
    draw.line([(sep, int(60 * scale)), (sep, height - int(60 * scale))],
              fill=(58, 75, 108), width=2)

    right = width - int(70 * scale)
    rtext(draw, (right, int(78 * scale)), "همراه قطعی",
          font(int(78 * scale), bold=True), TEXT)
    draw.text((right, int(176 * scale)), "Hamrah Ghatie", font=font(int(34 * scale), bold=True),
              fill=ACCENT, anchor="ra")
    draw.text((right, int(222 * scale)), "Offline Internet Blackout Companion",
              font=font(int(23 * scale)), fill=MUTED, anchor="ra")
    rtext(draw, (right, int(278 * scale)), "۱۰۰٪ آفلاین  •  ویندوز ۱۰/۱۱  •  فارسی و راستبهچپ",
          font(int(22 * scale)), TEXT)
    draw.text((right, int(330 * scale)), "github.com/ShayanTxT/hamrah-ghatie",
              font=font(int(20 * scale)), fill=MUTED, anchor="ra")

    path = OUT / filename
    img.save(path, optimize=True)
    print(f"✅ {path} ({width}×{height})")
    return path


if __name__ == "__main__":
    build(1280, 420, "banner.png")
    build(1280, 640, "social-preview.png")
