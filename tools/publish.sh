#!/usr/bin/env bash
# انتشار روی گیتهاب / Publish to GitHub
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=========================================================="
echo "  Publish to GitHub: https://github.com/ShayanTxT/hamrah-ghatie"
echo "=========================================================="

command -v git >/dev/null || { echo "Git is not installed."; exit 1; }

if [ ! -d .git ]; then
    echo "[1/5] git init"
    git init
    git branch -M main
fi

if ! git remote get-url origin >/dev/null 2>&1; then
    echo "[2/5] add remote"
    git remote add origin https://github.com/ShayanTxT/hamrah-ghatie.git
else
    echo "[2/5] remote already exists"
fi

echo "[3/5] checking for private files"
if git status --short | grep -E 'data/app\.db|identity\.json|peers\.json' >/dev/null 2>&1; then
    echo "  ⚠ Private files detected in the staging list — check .gitignore."
fi

echo "[4/5] commit"
git add .
if ! git diff --cached --quiet; then
    git commit -m "feat: initial release of Hamrah Ghatie v1.0.0"
else
    echo "  nothing to commit"
fi

echo "[5/5] push to main"
git push -u origin main

echo
echo "✅ Done! Next:"
echo "   Actions → Build Windows portable → Run workflow"
echo "   Or tag:  git tag -a v1.0.0 -m 'v1.0.0' && git push origin v1.0.0"
echo "   Then upload .github/assets/social-preview.png in Settings → General."
echo "   Full checklist: .github/REPO_SETUP.md"
