#!/usr/bin/env bash
# macOS: направи този файл изпълним ВЕДНЪЖ (виж README.md), после
# просто го отваряш с двоен клик — генерира таблото и го отваря в
# браузъра автоматично.
set -e
cd "$(dirname "$0")"

echo "Инсталирам/обновявам необходимите Python библиотеки (тихо)..."
python3 -m pip install --quiet -r requirements.txt

echo "Генерирам таблото..."
python3 dashboard.py
