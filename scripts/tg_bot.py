#!/usr/bin/env python3
"""
tg_bot.py — Personal DM Telegram bot for whisperX pipeline.

Sirf ALLOWED_USER_IDS me listed Telegram user IDs ke bheje hue
files process karega. Kisi aur ka message aaye to CHUP-CHAAP ignore
kar dega (koi reply nahi jayega).

Setup (Termux):
    pip install pyrogram tgcrypto requests

    export TG_API_ID=xxxxx          # my.telegram.org
    export TG_API_HASH=xxxxxxxxxxxx
    export TG_BOT_TOKEN=xxxxxx:yyyy
    export TG_ALLOWED_USER_IDS="111111111,222222222"   # tumhara ID, dost ka ID
    export GH_TOKEN=ghp_xxxx        # PAT: repo + workflow scopes
    export GH_OWNER=VOIDx777
    export GH_REPO=whisperX
    export GH_WORKFLOW_FILE=generate.yml
    export GH_BRANCH=main

Apna Telegram user ID pata karne ke liye: bot se DM me koi bhi text
bhejo (allowlist khali rakh ke test run karo), console log me ID print
hoga — usko allowlist me daal do.

Run:
    python scripts/tg_bot.py
"""

import os
import uuid
import requests
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
BOT_TOKEN = os.environ["TG_BOT_TOKEN"]
GH_TOKEN = os.environ["GH_TOKEN"]
GH_OWNER = os.environ.get("GH_OWNER", "VOIDx777")
GH_REPO = os.environ.get("GH_REPO", "whisperX")
GH_WORKFLOW_FILE = os.environ.get("GH_WORKFLOW_FILE", "generate.yml")
GH_BRANCH = os.environ.get("GH_BRANCH", "main")

ALLOWED_USER_IDS = {
    int(x) for x in os.environ.get("TG_ALLOWED_USER_IDS", "").split(",") if x.strip()
}

MODELS = ["large-v3", "medium", "small", "distil-large-v3"]

GH_API = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
}

app = Client("tgbot_dm", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

pending = {}  # job_id -> pyrogram Message


def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USER_IDS:
        # allowlist khali hai -> abhi setup mode, sabko log karo par process mat karo
        return False
    return user_id in ALLOWED_USER_IDS


def model_keyboard(job_id):
    rows, row = [], []
    for i, m in enumerate(MODELS, 1):
        row.append(InlineKeyboardButton(m, callback_data=f"m:{job_id}:{m}"))
        if i % 2 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


@app.on_message(filters.private & filters.text & ~filters.me)
async def on_any_text(client, message):
    uid = message.from_user.id if message.from_user else None
    if uid is None:
        return
    if not is_allowed(uid):
        print(f"[ignored] unauthorized user_id={uid} username={message.from_user.username}")
        return  # chup-chaap ignore
    if message.text and message.text.startswith("/start"):
        await message.reply_text("Ready hoon. Mp3/mp4/opus file bhejo.")


@app.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def on_media(client, message):
    uid = message.from_user.id if message.from_user else None
    if uid is None or not is_allowed(uid):
        print(f"[ignored file] unauthorized user_id={uid}")
        return  # kisi aur ki file ko touch tak nahi karna

    job_id = uuid.uuid4().hex[:10]
    pending[job_id] = message
    await message.reply_text(
        "🎙 Model chuno is file ke liye:",
        quote=True,
        reply_markup=model_keyboard(job_id),
    )


@app.on_callback_query(filters.regex(r"^m:"))
async def on_model_pick(client, cq):
    uid = cq.from_user.id if cq.from_user else None
    if uid is None or not is_allowed(uid):
        return await cq.answer("Not authorized.", show_alert=False)

    _, job_id, model = cq.data.split(":", 2)
    src_message = pending.get(job_id)
    if not src_message:
        return await cq.answer("Job expire ho gaya, file dobara bhejo.", show_alert=True)

    await cq.answer()
    status = await cq.message.edit_text(f"⬇️ Downloading… (model={model})")

    async def dl_progress(current, total):
        pct = current * 100 / total
        try:
            await status.edit_text(f"⬇️ Downloading… {pct:.0f}% (model={model})")
        except Exception:
            pass

    local_path = await src_message.download(progress=dl_progress)

    await status.edit_text("☁️ Temp storage pe upload ho raha hai…")

    tag = f"job-{job_id}"
    rel = requests.post(
        f"{GH_API}/repos/{GH_OWNER}/{GH_REPO}/releases",
        headers=HEADERS,
        json={
            "tag_name": tag,
            "name": tag,
            "prerelease": True,
            "body": "temp input asset - workflow isko delete kar dega processing ke baad",
        },
    ).json()
    upload_url = rel["upload_url"].split("{")[0]
    filename = os.path.basename(local_path)
    with open(local_path, "rb") as f:
        up = requests.post(
            f"{upload_url}?name={filename}",
            headers={**HEADERS, "Content-Type": "application/octet-stream"},
            data=f,
        ).json()
    asset_id = up["id"]
    os.remove(local_path)

    await status.edit_text("🚀 Workflow trigger ho raha hai…")

    resp = requests.post(
        f"{GH_API}/repos/{GH_OWNER}/{GH_REPO}/actions/workflows/{GH_WORKFLOW_FILE}/dispatches",
        headers=HEADERS,
        json={
            "ref": GH_BRANCH,
            "inputs": {
                "model": model,
                "language": "auto",
                "mode": "asr",
                "job_id": job_id,
                "release_tag": tag,
                "asset_id": str(asset_id),
                "tg_chat_id": str(src_message.chat.id),
                "tg_status_msg_id": str(status.id),
                "tg_reply_to_msg_id": str(src_message.id),
            },
        },
    )
    if resp.status_code >= 300:
        await status.edit_text(f"❌ Trigger fail: {resp.status_code} {resp.text[:200]}")
        return

    await status.edit_text(
        f"✅ Queued — job `{job_id}`, model=`{model}`.\nProgress yahin update hoga."
    )
    pending.pop(job_id, None)


if __name__ == "__main__":
    if not ALLOWED_USER_IDS:
        print("⚠️  TG_ALLOWED_USER_IDS khali hai — sab messages sirf log honge, process kuch nahi hoga.")
        print("    Bot ko DM karo, terminal me apna user_id dekhega, use env var me daal do.")
    print("tg_bot.py running…")
    app.run()
