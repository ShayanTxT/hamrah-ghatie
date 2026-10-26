# -*- mode: python ; coding: utf-8 -*-
"""مشخصات بستهبندی PyInstaller — خروجی onedir پرتابل (بدون نصب)."""
from PyInstaller.utils.hooks import collect_all  # noqa: E402

datas = [("assets", "assets")]
binaries = []
hiddenimports = [
    "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
    "PySide6.QtNetwork", "PySide6.QtSvg",
    "sqlite3", "pypdf", "zstandard", "psutil", "cryptography",
]

# جمعآوری خودکار وابستگیهایی که فایلهای باینری/داده دارند.
# در صورت نصب نبودن یک بستهٔ اختیاری، ساخت متوقف نمیشود.
for package in ("libzim", "zstandard", "pypdf", "psutil", "cryptography"):
    try:
        d, b, h = collect_all(package)
        datas += d
        binaries += b
        hiddenimports += h
        print(f"[spec] collected {package}: {len(d)} data, {len(b)} binaries")
    except Exception as exc:  # pragma: no cover - فقط هنگام ساخت
        print(f"[spec] skip {package}: {exc}")

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "numpy", "scipy", "PIL", "pytest",
        "IPython", "notebook", "setuptools", "pip", "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtMultimedia",
    ],
    noarchive=False,
    optimize=0,
)

# ترجمههای ازپیشساختهای Qt (حدود ۷ مگ، ۹۹ فایل qm) لازم نیستند؛
# متنهای خود برنامه فارسی هستند و Qt بدون آنها هم راه میافتد.
a.datas = [entry for entry in a.datas
           if "translations" not in str(entry[0]).replace("\\", "/").lower()]

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HamrahGhatie",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # برنامهٔ پنجرهای، بدون کنسول سیاه
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="HamrahGhatie",
)
