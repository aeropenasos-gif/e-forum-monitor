#!/usr/bin/env bash
# Пуска таблото за преглед (dashboard.py) и го отваря автоматично в
# браузъра. За Mac/Linux. Ако предпочиташ двукликване с икона на Mac,
# ползвай run_dashboard.command (същото съдържание, друго разширение).
set -e
cd "$(dirname "$0")"

echo "Инсталирам/обновявам необходимите Python библиотеки (тихо)..."
python3 -m pip install --quiet -r requirements.txt

echo "Генерирам таблото..."
python3 dashboard.py
