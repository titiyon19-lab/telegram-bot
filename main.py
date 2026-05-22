"""
Awche Lottery — Telegram Registration Bot
Railway production deployment — pure polling, no web server.

Conversation flow
-----------------
/start               → greet user, ask Transaction ID
Transaction ID       → .strip().upper() → Airtable lookup → ask Phone
Phone (digits only)  → validate → ask Full Name & City
Full Name & City     → save to Airtable → success message
"""

from __future__ import annotations

import html
import logging
import os
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

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("awche_bot")

# ---------------------------------------------------------------------------
# Environment — fail fast with a clear message if anything is missing
# ---------------------------------------------------------------------------

def _require(key: str, default: str = "") -> str:
    value = os.environ.get(key, default).strip()
    if not value and not default:
        raise SystemExit(f"[FATAL] environment variable '{key}' is not set")
    return value


TOKEN          = _require("TELEGRAM_BOT_TOKEN")
AIRTABLE_KEY   = _require("AIRTABLE_API_KEY")
AIRTABLE_BASE  = _require("AIRTABLE_BASE_ID",    "appa4GoH54MAPKcUT")
AIRTABLE_TABLE = _require("AIRTABLE_TABLE_NAME", "tblqr6cf0PQA5Zwel")

# ---------------------------------------------------------------------------
# Airtable
# ---------------------------------------------------------------------------

airtable_table = Api(AIRTABLE_KEY).table(AIRTABLE_BASE, AIRTABLE_TABLE)

# ---------------------------------------------------------------------------
# Conversation states
# ---------------------------------------------------------------------------

AWAITING_TRANSACTION, AWAITING_PHONE, AWAITING_NAME_CITY = range(3)

# ---------------------------------------------------------------------------
# Message templates
# ---------------------------------------------------------------------------

MSG_PLEASE_START = "እባክዎ 👉 /start ይጫኑ ለመጀመር።"

MSG_SUCCESS = (
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

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context) -> int:
    """Entry point: send receipt sample photo with caption, prompt for Transaction ID."""
    context.user_data.clear()
    first_name = (update.effective_user.first_name or "").strip()
    caption = (
        f"እንኳን ደህና መጡ! 🎉 {first_name}\n\n"
        "እባክዎ የባንክ ደረሰኝ የ Transaction ID ቁጥሩን ፅፈው ይላኩ FT የሚጀምር።"
    )
    try:
        with open("receipt_sample.png", "rb") as photo:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo,
                caption=caption,
            )
    except FileNotFoundError:
        log.warning("receipt_sample.png not found — sending text only")
        await update.message.reply_text(caption)
    return AWAITING_TRANSACTION


async def handle_transaction(update: Update, context) -> int:
    """Step 1: normalise FT ID, look up in Airtable, prompt for phone."""
    txn_id = (update.message.text or "").strip().upper()

    if not txn_id:
        await update.message.reply_text("እባክዎ Transaction ID ያስገቡ (FT የሚጀምር)")
        return AWAITING_TRANSACTION

    log.info("lookup txn=%s chat=%s", txn_id, update.effective_chat.id)

    try:
        records = airtable_table.all(
            formula=match({"Transaction ID": txn_id}),
            max_records=1,
        )
    except Exception as exc:
        log.error("Airtable lookup error: %s", exc)
        await update.message.reply_text("ስህተት ተፈጥሯል፣ እባክዎ ቆይተው ይሞክሩ።")
        return ConversationHandler.END

    if not records:
        await update.message.reply_text(
            "ይቅርታ፣ ይህ Transaction ID አልተገኘም።\n"
            "እባክዎ ትክክለኛ FT ቁጥር ያስገቡ ወይም ቆይቶ ይሞክሩ።"
        )
        return AWAITING_TRANSACTION

    record = records[0]
    fields = record.get("fields", {})

    # Duplicate check
    if str(fields.get("Chat ID", "") or "").strip():
        p_name  = html.escape(str(fields.get("Full Name",      "") or "—"))
        p_lotto = html.escape(str(fields.get("Lottery number", "") or "—"))
        await update.message.reply_text(
            "⚠️ <b>ይህ Transaction ID ቀድሞ ተመዝግቧል!</b>\n\n"
            f"ስም፦ {p_name}\n"
            f"የዕጣ ቁጥር፦ {p_lotto}",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    context.user_data["record_id"] = record["id"]
    await update.message.reply_text("እባክዎ ስልክ ቁጥርዎን ያስገቡ (ቁጥር ብቻ)")
    return AWAITING_PHONE


async def handle_phone(update: Update, context) -> int:
    """Step 2: digits-only validation, then prompt for name + city."""
    phone = (update.message.text or "").strip()

    if not phone.isdigit():
        await update.message.reply_text("እባክዎ ስልክ ቁጥርዎን ያስገቡ (ቁጥር ብቻ)")
        return AWAITING_PHONE

    context.user_data["phone"] = phone
    await update.message.reply_text("እባክዎ ሙሉ ስምዎትና የሚኖሩት ከተማ ያስገቡ")
    return AWAITING_NAME_CITY


async def handle_name_city(update: Update, context) -> int:
    """Step 3: save full name + city + phone + username to Airtable, show success."""
    text = (update.message.text or "").strip()

    if not text:
        await update.message.reply_text("እባክዎ ሙሉ ስምዎትና የሚኖሩት ከተማ ያስገቡ")
        return AWAITING_NAME_CITY

    record_id = context.user_data.get("record_id")
    phone     = context.user_data.get("phone", "")

    if not record_id:
        await update.message.reply_text(MSG_PLEASE_START)
        return ConversationHandler.END

    user     = update.effective_user
    chat_id  = update.effective_chat.id
    username = f"@{user.username}" if (user and user.username) else ""

    log.info("save record=%s chat=%s", record_id, chat_id)

    try:
        result = airtable_table.update(
            record_id,
            {
                "Full Name":   text,
                "User mobile": phone,
                "Chat ID":     str(chat_id),
                "Status":      "Verified",
            },
            typecast=True,
        )
    except Exception as exc:
        log.error("Airtable save error: %s", exc)
        await update.message.reply_text("ስህተት ተፈጥሯል፣ እባክዎ ቆይተው ይሞክሩ።")
        return ConversationHandler.END

    lottery_number = html.escape(
        str(result.get("fields", {}).get("Lottery number", "") or "")
    )
    await update.message.reply_text(
        MSG_SUCCESS.format(lottery_number=lottery_number),
        parse_mode="HTML",
        disable_web_page_preview=False,
    )
    return ConversationHandler.END


async def fallback_in_conversation(update: Update, context) -> int:
    """Catch-all inside an active conversation (unsupported message type, etc.)."""
    if update.message:
        await update.message.reply_text(MSG_PLEASE_START)
    return ConversationHandler.END


async def catch_all_outside(update: Update, context) -> None:
    """Catch-all outside the conversation (user has not started or flow ended)."""
    if update.message:
        await update.message.reply_text(MSG_PLEASE_START)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(MSG_PLEASE_START)


# ---------------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("Bot starting…")

    app = Application.builder().token(TOKEN).build()

    conversation = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            AWAITING_TRANSACTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_transaction),
            ],
            AWAITING_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone),
            ],
            AWAITING_NAME_CITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name_city),
            ],
        },
        fallbacks=[
            CommandHandler("start", cmd_start),
            MessageHandler(filters.ALL, fallback_in_conversation),
        ],
        allow_reentry=True,
    )

    app.add_handler(conversation)

    # Handles messages from users with no active conversation
    app.add_handler(MessageHandler(filters.ALL, catch_all_outside))

    log.info("Polling started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
