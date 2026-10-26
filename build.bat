@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   ساخت نسخهٔ پرتابل ویندوزی «همراه قطعی»
echo   Hamrah Ghatie - portable Windows build
echo   نیازمند: Python 3.11 x64 (Windows 10/11) + اینترنت برای pip
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [خطا] Python پیدا نشد. اول Python 3.11 x64 را نصب کنید و Add to PATH بزنید.
    exit /b 1
)

python -c "import sys; assert sys.version_info[:2]==(3,11), 'Python 3.11 لازم است'; assert sys.maxsize>2**32, 'نسخهٔ ۶۴بیتی لازم است'" || (
    echo [خطا] نسخهٔ Python باید ۳٫۱۱ و ۶۴بیتی باشد.
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/6] ساخت محیط مجازی...
    python -m venv .venv || exit /b 1
)
call .venv\Scripts\activate.bat

echo [2/6] نصب وابستگیها...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || exit /b 1
python -m pip install -r requirements-build.txt || exit /b 1
if /I "%~1"=="--with-libzim" (
    echo    نصب پشتیبان اختیاری libzim ^(GPLv3^)...
    python -m pip install -r requirements-optional.txt || echo [هشدار] libzim نصب نشد؛ خوانندهٔ بومی ZIM همچنان کار میکند.
) else (
    echo    libzim اختیاری نصب نشد (خوانندهٔ بومی ZIM کافی است).
    echo    برای اضافه کردنش: build.bat --with-libzim
)

echo [3/6] اجرای تستها...
python -m pip install pytest -q
python -m pytest -q tests
if errorlevel 1 (
    echo [خطا] تستها passed نشدند؛ ساخت متوقف شد.
    exit /b 1
)

echo [4/6] بستهبندی با PyInstaller (چند دقیقه طول میکشد)...
pyinstaller --noconfirm --clean hamrah-ghatie.spec || exit /b 1

echo [5/6] آمادهسازی پوشهٔ نهایی...
if exist "dist\همراه قطعی" rmdir /s /q "dist\همراه قطعی"
move "dist\HamrahGhatie" "dist\همراه قطعی" >nul
set "DEST=dist\همراه قطعی"
for %%D in (downloads pages library "library\zim" models bin incoming exports logs tmp) do (
    if not exist "%DEST%\data\%%D" mkdir "%DEST%\data\%%D" 2>nul
)
if not exist "%DEST%\docs" mkdir "%DEST%\docs"
if not exist "%DEST%\samples" mkdir "%DEST%\samples"
for %%F in (README.md README.fa.md README.en.md LICENSE LICENSE-THIRD-PARTY.md CHANGELOG.md CONTRIBUTING.md SECURITY.md SUPPORT.md CODE_OF_CONDUCT.md) do (
    copy /Y "%%F" "%DEST%\%%F" >nul
)
copy /Y "docs\ARCHITECTURE.md" "%DEST%\docs\ARCHITECTURE.md" >nul
if exist "docs\screenshots" xcopy /E /I /Y "docs\screenshots" "%DEST%\docs\screenshots" >nul
if exist "samples\*.zim" copy /Y "samples\*.zim" "%DEST%\samples\" >nul
if exist "assets\fonts\OFL.txt" copy /Y "assets\fonts\OFL.txt" "%DEST%\assets\fonts\OFL.txt" >nul
echo فایل اجرایی: HamrahGhatie.exe ^| مستندات: README.fa.md > "%DEST%\data\راهنما.txt"

echo [6/6] ساخت ZIP و هش SHA-256...
if exist "dist\همراه_قطعی_پرتابل.zip" del "dist\همراه_قطعی_پرتابل.zip"
powershell -NoProfile -Command "Compress-Archive -Path '%DEST%' -DestinationPath 'dist\همراه_قطعی_پرتابل.zip' -Force; (Get-FileHash 'dist\همراه_قطعی_پرتابل.zip' -Algorithm SHA256).Hash | Out-File -Encoding utf8 'dist\SHA256SUMS.txt'"

echo.
echo ============================================================
echo   تمام! خروجی:
echo     dist\همراه قطعی\HamrahGhatie.exe
echo     dist\همراه_قطعی_پرتابل.zip  +  SHA256SUMS.txt
echo   پوشهٔ data کنار exe است؛ با کپی کردن کل پوشه همهچیز منتقل میشود.
echo ============================================================
endlocal
