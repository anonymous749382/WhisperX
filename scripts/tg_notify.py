#!/usr/bin/env python3
"""
tg_notify.py — GitHub Actions runner ke andar se TG me rich progress
card dikhane aur final zip bhejne ke liye. Sirf `requests` chahiye.

Usage:
    python tg_notify.py edit  <chat_id> <message_id> "<text>"
    python tg_notify.py stage <chat_id> <message_id> <job_id> <filename> <model> <start_epoch> <stage_key> [run_url]
    python tg_notify.py fail  <chat_id> <message_id> <job_id> [run_url]
    python tg_notify.py send  <chat_id> <reply_to_id> <file_path> ["<caption>"]

stage_key one of: fetching | transcribing | aligning | done

Env:
    TELEGRAM_BOT_TOKEN  (GitHub repo secret se aayega)
"""
import os
import sys
import time
import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

STAGES = [
    ("fetching", "📥 Fetching input"),
    ("transcribing", "🧠 Transcribing"),
    ("aligning", "🎯 Aligning & packaging"),
    ("done", "📦 Uploading result"),
]


def _fmt_elapsed(start_epoch) -> str:
    try:
        s = int(time.time() - float(start_epoch))
    except Exception:
        return "--:--"
    s = max(s, 0)
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"


def build_card(job_id, filename, model, start_epoch, stage_key, run_url=None) -> str:
    idx = next((i for i, (k, _) in enumerate(STAGES) if k == stage_key), 0)
    lines = [
        f"🎬 {filename}",
        f"🔧 model: `{model}`   🆔 `{job_id}`",
        f"⏱ {_fmt_elapsed(start_epoch)} elapsed",
        "",
    ]
    for i, (_, label) in enumerate(STAGES):
        if i < idx:
            mark = "✅"
        elif i == idx:
            mark = "⏳"
        else:
            mark = "⬜"
        lines.append(f"{mark} {label}")
    if run_url:
        lines.append("")
        lines.append(f"🔗 [Actions run]({run_url})")
    return "\n".join(lines)


def edit(chat_id, message_id, text, markdown=False):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if markdown:
        payload["parse_mode"] = "Markdown"
        payload["disable_web_page_preview"] = True
    r = requests.post(f"{API}/editMessageText", json=payload, timeout=30)
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

    elif action == "stage":
        chat_id, message_id, job_id, filename, model, start_epoch, stage_key = sys.argv[2:9]
        run_url = sys.argv[9] if len(sys.argv) > 9 and sys.argv[9] else None
        text = build_card(job_id, filename, model, start_epoch, stage_key, run_url)
        edit(chat_id, message_id, text, markdown=True)

    elif action == "fail":
        chat_id, message_id, job_id = sys.argv[2:5]
        run_url = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else None
        text = f"❌ Job `{job_id}` fail ho gaya."
        if run_url:
            text += f"\n🔗 [Logs dekho]({run_url})"
        edit(chat_id, message_id, text, markdown=True)

    elif action == "send":
        caption = sys.argv[5] if len(sys.argv) > 5 else ""
        send_document(sys.argv[2], sys.argv[3], sys.argv[4], caption)

    else:
        print("unknown action", file=sys.stderr)
        sys.exit(1)
