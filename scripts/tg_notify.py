#!/usr/bin/env python3
"""
tg_notify.py — GitHub Actions runner ke andar se TG me progress edit
karne aur final zip bhejne ke liye. Sirf `requests` chahiye.

Usage:
    python tg_notify.py edit  <chat_id> <message_id> "<text>"
    python tg_notify.py send  <chat_id> <reply_to_id> <file_path> ["<caption>"]

Env:
    TELEGRAM_BOT_TOKEN  (GitHub repo secret se aayega)
"""
import os
import sys
import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def edit(chat_id, message_id, text):
    r = requests.post(
        f"{API}/editMessageText",
        json={"chat_id": chat_id, "message_id": message_id, "text": text},
        timeout=30,
    )
    if not r.ok:
        print("tg edit failed:", r.text, file=sys.stderr)


def send_document(chat_id, reply_to, path, caption=""):
    with open(path, "rb") as f:
        r = requests.post(
            f"{API}/sendDocument",
            data={
                "chat_id": chat_id,
                "reply_to_message_id": reply_to,
                "caption": caption,
            },
            files={"document": f},
            timeout=300,
        )
    if not r.ok:
        print("tg send failed:", r.text, file=sys.stderr)


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "edit":
        edit(sys.argv[2], sys.argv[3], sys.argv[4])
    elif action == "send":
        caption = sys.argv[5] if len(sys.argv) > 5 else ""
        send_document(sys.argv[2], sys.argv[3], sys.argv[4], caption)
    else:
        print("unknown action", file=sys.stderr)
        sys.exit(1)
