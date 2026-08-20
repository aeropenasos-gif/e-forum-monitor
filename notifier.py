"""
notifier.py
-----------
Изпращане на известия през Telegram и e-mail.

Telegram: изпраща се ВЕДНАГА по едно кратко съобщение за всяко ново
съвпадение (бърз и безплатен канал).

E-mail: съвпаденията от един цикъл на проверка се събират в ЕДИН общ
дигест-имейл (за да не се "наводнява" пощата при повече съвпадения
наведнъж). Ако искаш имейл за всяко съвпадение поотделно, виж
README.md -> "Промяна на поведението на известията".

Нужни "тайни" стойности (GitHub Secrets):
    TELEGRAM_BOT_TOKEN
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM (по избор)
"""

import os
import smtplib
from email.mime.text import MIMEText

import requests


def format_match_message(item: dict, matches: list) -> str:
    phrases = ", ".join(sorted({m["phrase"] for m in matches}))
    return (
        f"🔔 Ново релевантно съобщение — {item['source_label']}\n"
        f"Ключова фраза/асоциация: {phrases}\n"
        f"Линк: {item['url']}"
    )


def send_telegram(text: str, chat_id: str) -> bool:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if not bot_token or not chat_id:
        print("[notifier] Пропускам Telegram — липсва bot token или chat_id.")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        response = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": False,
            },
            timeout=15,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        print(f"[notifier] Грешка при изпращане в Telegram: {exc}")
        return False


def send_email_digest(matched_items_with_matches, to_addresses) -> bool:
    """
    matched_items_with_matches: списък от (item, matches) двойки.
    """
    if not matched_items_with_matches:
        return True

    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    email_from = os.environ.get("EMAIL_FROM") or smtp_user

    if not smtp_user or not smtp_pass or not to_addresses:
        print("[notifier] Пропускам e-mail — липсват SMTP данни или получатели.")
        return False

    lines = [
        f"Открити са {len(matched_items_with_matches)} нови релевантни съобщения:\n"
    ]
    for item, matches in matched_items_with_matches:
        phrases = ", ".join(sorted({m["phrase"] for m in matches}))
        lines.append(f"— {item['source_label']}")
        lines.append(f"  Ключова фраза/асоциация: {phrases}")
        lines.append(f"  Линк: {item['url']}")
        lines.append("")

    body = "\n".join(lines)
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = f"Eligna Forum Monitor — {len(matched_items_with_matches)} нови съвпадения"
    msg["From"] = email_from
    msg["To"] = ", ".join(to_addresses)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(email_from, to_addresses, msg.as_string())
        return True
    except Exception as exc:  # noqa: BLE001 — искаме да логваме всякаква грешка тук
        print(f"[notifier] Грешка при изпращане на e-mail: {exc}")
        return False
