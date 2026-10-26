@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0\.."

echo ==========================================================
echo   انتشار پروژه روی گیتهاب / Publish to GitHub
echo   https://github.com/ShayanTxT/hamrah-ghatie
echo ==========================================================
echo.

where git >nul 2>nul
if errorlevel 1 (
    echo [خطا] Git نصب نیست. از https://git-scm.com/downloads بگیرید.
    exit /b 1
)

if not exist ".git" (
    echo [1/5] git init
    git init || exit /b 1
    git branch -M main
)

git remote get-url origin >nul 2>nul
if errorlevel 1 (
    echo [2/5] اضافه کردن remote
    git remote add origin https://github.com/ShayanTxT/hamrah-ghatie.git || exit /b 1
) else (
    echo [2/5] remote از قبل وجود دارد.
)

echo [3/5] بررسی فایلهای حساس...
git status --short | findstr /C:"data/app.db" /C:"identity.json" /C:"peers.json" >nul
if not errorlevel 1 (
    echo [هشدار] فایلهای شخصی در لیست پوش دیده شدند. .gitignore را چک کنید.
)

echo [4/5] کامیت
git add .
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "feat: initial release of Hamrah Ghatie v1.0.0" || exit /b 1
) else (
    echo      تغییری برای کامیت نیست.
)

echo [5/5] پوش به main
git push -u origin main || (
    echo.
    echo [خطا] پوش انجام نشد. مطمئن شوید ریپو در گیتهاب ساخته شده و لاگین کردهاید.
    exit /b 1
)

echo.
echo ✅ انجام شد! حالا:
echo    Actions → Build Windows portable → Run workflow
echo    یا تگ بزنید:  git tag -a v1.0.0 -m "v1.0.0" ^&^& git push origin v1.0.0
echo    سپس Settings → General → Social preview را آپلود کنید.
echo    چکلیست کامل: .github\REPO_SETUP.md
endlocal
