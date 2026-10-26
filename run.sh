#!/usr/bin/env bash
# اجرای برنامه در محیط لینوکس/مک (برای توسعه و تست)
set -e
cd "$(dirname "$0")"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
python3 run.py "$@"
