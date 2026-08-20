@echo off
REM Windows: двукликни този файл — генерира таблото и го отваря
REM автоматично в браузъра.
cd /d "%~dp0"

echo Инсталирам/обновявам необходимите Python библиотеки (тихо)...
python -m pip install --quiet -r requirements.txt

echo Генерирам таблото...
python dashboard.py

pause
