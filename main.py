"""
Awche Lottery — Telegram Bot  (Railway / Production)
-----------------------------------------------------
Flow:
  /start → ask Transaction ID (FT...)
  FT ID  → Airtable exact lookup → ask Full Name + City
  Name   → ask Mobile number
  Mobile → save to Airtable → return Lottery number

Pure polling worker — no HTTP server, no PORT binding.
"""

from __future__ import annotations

import html
import logging
import os
import re
import sys

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)
from pyairtable import Api
from pyairtable.formulas import match

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("awche_bot")

# ── Environment ───────────────────────────────────────────────────────────────

def _env(key: str, default: str = "") -> str:
    val = os.environ.get(key, default).strip()
    if not val and not default:
        raise SystemExit(f"[FATAL] Missing env var: {key}")
    return val

TOKEN          = _env("TELEGRAM_BOT_TOKEN")
AIRTABLE_KEY   = _env("AIRTABLE_API_KEY")
AIRTABLE_BASE  = _env("AIRTABLE_BASE_ID",    "appa4GoH54MAPKcUT")
AIRTABLE_TABLE = _env("AIRTABLE_TABLE_NAME", "tblqr6cf0PQA5Zwel")

# ── Airtable client ───────────────────────────────────────────────────────────

table = Api(AIRTABLE_KEY).table(AIRTABLE_BASE, AIRTABLE_TABLE)

# ── ConversationHandler states ────────────────────────────────────────────────

AWAITING_TRANSACTION, AWAITING_NAME_CITY, AWAITING_MOBILE = range(3)

# ── Static messages ───────────────────────────────────────────────────────────

_PLEASE_START = "እባክዎ 👉 /start ይጫኑ ለመጀመር።"

_SUCCESS = (
    "✅ ምዝገባዎ በተሳካ ሁኔታ ተጠናቅቋል!\n"
    "\n"
    "🎫 የእርስዎ የዕጣ ቁጥር፦ <b>{lottery_number}</b>\n"
    "\n"
    "🍀 መልካም ዕድል!\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "ዓውቸ Online Lottery\n"
    "\n"
    "📺 ዕጣው በቀጥታ (Live) የሚተላለፍባቸው አድራሻዎች፦\n"
    "\n"
    "Telegram:\nhttps://t.me/+hNcPdZTTL-xhMjhk\n"
    "\n"
    "YouTube:\nhttps://youtube.com/@awuchetube?si=gS48mTKirCFoFSRK\n"
    "\n"
    "TikTok:\nhttps://www.tiktok.com/@awuch66\n"
    "\n"
    "Facebook:\nhttp://facebook.com/share/1DwpPzF9bQ"
)

# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context) -> int:
    first_name = (update.effective_user.first_name or "").strip()
    await update.message.reply_text(
        f"እንኳን ደህና መጡ! 🎉 {first_name}\n\n"
        "እባክዎ የባንክ Transaction ID ቁጥሩን ፅፈው ያስገቡ። FT የሚጀምር"
    )
    return AWAITING_TRANSACTION


async def receive_transaction(update: Update, context) -> int:
    txn_id = (update.message.text or "").strip().upper()
    if not txn_id:
        await update.message.reply_text("እባክዎ Transaction ID ያስገቡ (FT የሚጀምር)")
        return AWAITING_TRANSACTION

    log.info("lookup txn=%s chat=%s", txn_id, update.effective_chat.id)
    try:
        records = table.all(formula=match({"Transaction ID": txn_id}), max_records=1)
    except Exception as exc:
        log.error("Airtable lookup failed: %s", exc)
        await update.message.reply_text("ስህተት ተፈጥሯል፣ እባክዎ ቆይተው ይሞክሩ።")
        return ConversationHandler.END

    if not records:
        await update.message.reply_text(
            "ይቅርታ፣ ይህ Transaction ID አልተገኘም።\n"
            "እባክዎ ትክክለኛ FT... ቁጥር ያስገቡ ወይም ቆይቶ ይሞክሩ።"
        )
        return AWAITING_TRANSACTION

    record = records[0]
    fields = record.get("fields", {})

    # Already registered?
    if str(fields.get("Chat ID", "") or "").strip():
        p_name   = html.escape(str(fields.get("Full Name",      "") or "—"))
        p_mobile = html.escape(str(fields.get("User mobile",    "") or "—"))
        p_lotto  = html.escape(str(fields.get("Lottery number", "") or "—"))
        await update.message.reply_text(
            "⚠️ <b>ይህ Transaction ID ቀድሞ ተመዝግቧል!</b>\n\n"
            f"ስም፦ {p_name}\n"
            f"ስልክ፦ {p_mobile}\n"
            f"የዕጣ ቁጥር፦ {p_lotto}",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    context.user_data["record_id"] = record["id"]
    await update.message.reply_text("እባክዎ ሙሉ ስምዎን እና የሚኖሩበትን ከተማ ያስገቡ።")
    return AWAITING_NAME_CITY


async def receive_name_city(update: Update, context) -> int:
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("እባክዎ ሙሉ ስምዎን እና የሚኖሩበትን ከተማ ያስገቡ።")
        return AWAITING_NAME_CITY

    context.user_data["full_name"] = text
    await update.message.reply_text("እባክዎ ስልክ ቁጥርዎን ያስገቡ (ቁጥር ብቻ)")
    return AWAITING_MOBILE


async def receive_mobile(update: Update, context) -> int:
    mobile = (update.message.text or "").strip()
    if not re.fullmatch(r"\d{7,15}", mobile):
        await update.message.reply_text("⚠️ ትክክለኛ ሞባይል ቁጥር ያስገቡ (ቁጥር ብቻ)")
        return AWAITING_MOBILE

    record_id = context.user_data.get("record_id")
    full_name  = context.user_data.get("full_name", "")
    chat_id    = update.effective_chat.id

    log.info("save record=%s chat=%s", record_id, chat_id)
    try:
        updated = table.update(record_id, {
            "User mobile": mobile,
            "Chat ID":     str(chat_id),
            "Status":      "Verified",
            "Full Name":   full_name,
        }, typecast=True)
    except Exception as exc:
        log.error("Airtable save failed: %s", exc)
        await update.message.reply_text("ስህተት ተፈጥሯል፣ እባክዎ ቆይተው ይሞክሩ።")
        return ConversationHandler.END

    lottery_number = html.escape(
        str(updated.get("fields", {}).get("Lottery number", "") or "")
    )
    await update.message.reply_text(
        _SUCCESS.format(lottery_number=lottery_number),
        parse_mode="HTML",
        disable_web_page_preview=False,
    )
    return ConversationHandler.END


async def fallback(update: Update, context) -> int:
    await update.message.reply_text(_PLEASE_START)
    return ConversationHandler.END


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    log.info("Bot starting…")

    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            AWAITING_TRANSACTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_transaction)
            ],
            AWAITING_NAME_CITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name_city)
            ],
            AWAITING_MOBILE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_mobile)
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.ALL, fallback),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv)

    log.info("Polling started (drop_pending_updates=True)")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
