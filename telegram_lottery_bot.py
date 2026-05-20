"""
Telegram Lottery Bot
--------------------
Photo path:  /start → send receipt photo → OCR extracts ID + Name → ask mobile → save all → success
Manual path: /start → type Transaction ID → ask Full Name → ask Mobile → save all → success

Required environment variables:
    TELEGRAM_BOT_TOKEN   - Token from @BotFather
    AIRTABLE_API_KEY     - Airtable personal access token
    AIRTABLE_BASE_ID     - Defaults to "appa4GoH54MAPKcUT"
    AIRTABLE_TABLE_NAME  - Defaults to "tblqr6cf0PQA5Zwel"

Dependencies:
    pip install pyTelegramBotAPI==4.23.0 pyairtable==3.0.1 pytesseract Pillow
    System: tesseract
"""

import html
import io
import logging
import os
import re
import socket
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

import pytesseract
import telebot
from PIL import Image, ImageFilter
from pyairtable import Api
from pyairtable.formulas import match

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

_raw_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_TOKEN = _raw_token.strip()

# Validate token format: must be "<digits>:<alphanum>" with no spaces
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("[TOKEN] TELEGRAM_BOT_TOKEN secret is empty — please set it in Replit Secrets.")
if " " in TELEGRAM_BOT_TOKEN or "\n" in TELEGRAM_BOT_TOKEN:
    raise ValueError(
        f"[TOKEN] Token still contains whitespace after strip (raw length={len(_raw_token)}, "
        f"stripped length={len(TELEGRAM_BOT_TOKEN)}) — re-paste the token in Secrets."
    )
if ":" not in TELEGRAM_BOT_TOKEN:
    raise ValueError(
        f"[TOKEN] Token does not look valid (length={len(TELEGRAM_BOT_TOKEN)}, "
        f"no ':' separator found) — copy it fresh from BotFather."
    )
_token_parts = TELEGRAM_BOT_TOKEN.split(":", 1)
if not _token_parts[0].isdigit():
    raise ValueError(
        f"[TOKEN] Token prefix is not numeric (prefix={_token_parts[0]!r}) — copy it fresh from BotFather."
    )
print(
    f"[TOKEN] OK — length={len(TELEGRAM_BOT_TOKEN)}, "
    f"bot_id={_token_parts[0]}, "
    f"secret_preview=...{_token_parts[1][-6:]}",
    flush=True,
)

AIRTABLE_API_KEY = os.environ["AIRTABLE_API_KEY"]
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appa4GoH54MAPKcUT")
AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE_NAME", "tblqr6cf0PQA5Zwel")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
airtable = Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)

# Per-chat conversation state:
# {
#   "step":       "awaiting_transaction" | "awaiting_name" | "awaiting_mobile",
#   "record_id":  str | None,
#   "full_name":  str | None   <- from OCR or typed by user
# }
user_state: dict[int, dict] = {}

# ---------------------------------------------------------------------------
# Success message
# ---------------------------------------------------------------------------

SUCCESS_MESSAGE_TEMPLATE = (
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
    "Facebook:\nhttp://facebook.com/share/1DwpPzF9bQ\n"
)

# ---------------------------------------------------------------------------
# OCR helpers
# ---------------------------------------------------------------------------

_TXN_HEADERS = [
    r"Reference\s*No\.?\s*\(VAT\s*Invoice\s*No\.?\)",
    r"Reference\s*No\.?",
    r"Transaction\s*ID",
    r"Txn\s*ID",
    r"Ref\.?\s*No\.?",
]
_TXN_HEADER_RE = re.compile(
    r"(?:" + "|".join(_TXN_HEADERS) + r")\s*[:\-]?\s*([A-Za-z0-9]{6,})",
    re.IGNORECASE,
)
# ── CBE Mobile / "debited from" pattern ─────────────────────────────────────
# Uses [\s\S]+? (lazy, any character including newlines) so a triple Ethiopian
# name spread over two OCR lines is captured in full.
# Stops at the first occurrence of:
#   – the word "for"  (e.g. "debited from SELAMAWIT TADESSE BEKELE for ...")
#   – a hyphen / en-dash  (e.g. "...Gidey-ETB-9577")
_DEBITED_FROM_RE = re.compile(
    r"debited\s+from\s+"
    r"([\s\S]+?)"
    r"(?=\s+for\b|\s*[-–])",
    re.IGNORECASE,
)

# Strips account/amount suffixes that OCR may attach to extracted names:
#   "Gidey-ETB-9577"  →  "Gidey"
#   "Gebru - 1000.00" →  "Gebru"
_ACCOUNT_SUFFIX_RE = re.compile(
    r"\s*[-–]\s*(?:ETB|USD|EUR|GBP|Birr)[\s\-–]\S+.*"
    r"|\s*[-–]\s*\d[\d,\.]*.*",
    re.IGNORECASE,
)

# ── Generic label-based name patterns ───────────────────────────────────────
# Captures everything on the same line as the name label.
_NAME_HEADER_RE = re.compile(
    r"(?:Customer\s*Name|Payer\s*Name|Payer|Account\s*Name|Sender)\s*[:\-]?\s*([^\n]+)",
    re.IGNORECASE,
)

# Labels that mark where a name value ends (stop before these).
_NAME_STOP_RE = re.compile(
    r"\s*(?:City|Region|Wereda|Phone|Mobile|Tel|Amount|Date|Bank|Address|Sub\s*City|for\b|to\b)\s*[:\-]?",
    re.IGNORECASE,
)

_FT_BARE_RE = re.compile(r"\bFT[A-Z0-9]{4,}\b", re.IGNORECASE)


def _preprocess_image(image: Image.Image) -> Image.Image:
    w, h = image.size
    # Crop the top 10 % of the image to skip the phone notification/status bar,
    # which contains clocks, signal icons, and other noise that confuses OCR.
    top_crop = int(h * 0.10)
    image = image.crop((0, top_crop, w, h))
    return image.convert("L").filter(ImageFilter.SHARPEN)


def extract_data_from_image(photo_bytes: bytes) -> tuple[Optional[str], Optional[str]]:
    """Return (transaction_id, customer_name), either may be None."""
    image = _preprocess_image(Image.open(io.BytesIO(photo_bytes)))
    raw_text = pytesseract.image_to_string(image, config="--psm 6")
    # Always log the full raw OCR output for debugging purposes
    print(f"[OCR RAW TEXT]:\n{'-'*60}\n{raw_text}\n{'-'*60}", flush=True)

    # Transaction ID — header-prefixed match first, then bare FT token
    transaction_id: Optional[str] = None
    header_match = _TXN_HEADER_RE.search(raw_text)
    if header_match:
        candidate = header_match.group(1).upper().replace(" ", "")
        if re.match(r"FT[A-Z0-9]+", candidate):
            transaction_id = candidate
    bare = _FT_BARE_RE.findall(raw_text)
    if bare:
        transaction_id = bare[0].upper()

    # ── Customer name extraction ─────────────────────────────────────────────
    customer_name: Optional[str] = None

    def _clean_name(raw: str) -> Optional[str]:
        """
        1. Remove account/amount suffixes  e.g. "-ETB-9577" or "-9,000.00"
        2. Stop at boundary field labels   e.g. "City:", "Region:"
        3. Keep only valid name tokens:    letters, dots, forward-slashes
           (preserves Ethiopian abbreviations like H/MARIAM, G/MICHAEL)
        4. Title prefixes (Mr/Mrs/Ms/Dr) are kept as-is
        """
        # Step 1 — strip bank account / amount suffixes
        raw = _ACCOUNT_SUFFIX_RE.sub("", raw).strip()
        # Step 2 — stop before known boundary labels
        stop = _NAME_STOP_RE.search(raw)
        if stop:
            raw = raw[: stop.start()]
        # Step 3 — filter to name-like tokens (allow title words too)
        tokens = [
            t for t in raw.split()
            if re.match(r"[A-Za-z][A-Za-z\./]*\.?$", t)
        ]
        return " ".join(tokens) if tokens else None

    # Collapsed text (newlines → spaces) used for the label-based pattern which
    # is single-line by nature. The debited-from regex uses raw_text directly
    # because [\s\S]+? already crosses newlines natively.
    collapsed = re.sub(r"\n+", " ", raw_text)

    # Strip leading titles (Mr / Mrs / Ms / Dr, with or without dot) from a
    # name before checking minimum length, so "Mr Yonas" passes the guard
    # (core name "Yonas" is 5 chars) but "Mr" or "Mrs." alone is rejected.
    _TITLE_PREFIX_RE = re.compile(
        r"^(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?)\s+", re.IGNORECASE
    )

    def _name_passes_length(name: str) -> bool:
        core = _TITLE_PREFIX_RE.sub("", name).strip()
        return len(core) >= 3

    # Priority 1: CBE Mobile "debited from NAME for/– ..."
    # Search raw_text — [\s\S]+? handles names split across OCR lines natively.
    debited_match = _DEBITED_FROM_RE.search(raw_text)
    if debited_match:
        # Normalise any embedded newlines in the captured group to a single space
        raw_captured = re.sub(r"\s+", " ", debited_match.group(1)).strip()
        candidate = _clean_name(raw_captured)
        if candidate and _name_passes_length(candidate):
            customer_name = candidate
        elif candidate:
            print(f"[OCR] Discarded too-short name from debited-from: {candidate!r}", flush=True)

    # Priority 2: explicit label (Customer Name:, Payer Name:, Sender:, etc.)
    if not customer_name:
        label_match = _NAME_HEADER_RE.search(collapsed)
        if label_match:
            candidate = _clean_name(label_match.group(1))
            if candidate and _name_passes_length(candidate):
                customer_name = candidate
            elif candidate:
                print(f"[OCR] Discarded too-short name from label: {candidate!r}", flush=True)

    print(
        f"[OCR RESULT] Transaction ID={transaction_id!r}  Name={customer_name!r}",
        flush=True,
    )
    return transaction_id, customer_name


# ---------------------------------------------------------------------------
# Airtable helpers
# ---------------------------------------------------------------------------

def find_record_by_transaction_id(transaction_id: str) -> Optional[dict]:
    formula = match({"Transaction ID": transaction_id})
    records = airtable.all(formula=formula, max_records=1)
    return records[0] if records else None


def is_already_registered(fields: dict) -> bool:
    """True if the record already has a Chat ID (i.e. previously claimed)."""
    return bool(str(fields.get("Chat ID", "") or "").strip())


def update_record(
    record_id: str,
    mobile: str,
    chat_id: int,
    full_name: Optional[str] = None,
) -> dict:
    update_fields: dict = {
        "User mobile": mobile,
        "Chat ID": str(chat_id),
        "Status": "Verified",
    }
    if full_name:
        update_fields["Full Name"] = full_name

    try:
        return airtable.update(record_id, update_fields, typecast=True)
    except Exception as exc:
        print(
            f"[Airtable UPDATE ERROR] record_id={record_id!r} "
            f"fields={update_fields!r}: {exc!r}",
            flush=True,
        )
        traceback.print_exc()
        raise


# ---------------------------------------------------------------------------
# Shared lookup (used by photo and manual-text paths)
# ---------------------------------------------------------------------------

def lookup_and_advance(
    chat_id: int,
    transaction_id: str,
    full_name: Optional[str],
    came_from_photo: bool,
) -> None:
    """
    Validate the transaction ID in Airtable and move conversation state forward.

    Photo path:  if valid → go straight to awaiting_mobile (name already known)
    Manual path: if valid → go to awaiting_name first
    """
    try:
        record = find_record_by_transaction_id(transaction_id)
    except Exception as exc:
        print(
            f"[Airtable SEARCH ERROR] Transaction ID={transaction_id!r}: {exc!r}",
            flush=True,
        )
        traceback.print_exc()
        bot.send_message(chat_id, "ስህተት ተፈጥሯል፣ እባክዎ ቆይተው ይሞክሩ።")
        return

    if not record:
        bot.send_message(
            chat_id,
            "ይቅርታ፣ ይህ የትራንዛክሽን ቁጥር አልተገኘም። "
            "እባክዎ ትክክለኛ ደረሰኝ ይላኩ ወይም ቆይቶ ይሞክሩ።",
        )
        return

    fields = record.get("fields", {})
    if is_already_registered(fields):
        prev_name = html.escape(str(fields.get("Full Name", "") or "—"))
        prev_mobile = html.escape(str(fields.get("User mobile", "") or "—"))
        prev_lottery = html.escape(str(fields.get("Lottery number", "") or "—"))
        duplicate_msg = (
            "⚠️ <b>ይህ ደረሰኝ ቀድሞ ተመዝግቧል!</b>\n"
            "\n"
            "የቀድሞ ምዝገባ መረጃ፦\n"
            f"ስም፦ {prev_name}\n"
            f"ስልክ፦ {prev_mobile}\n"
            f"የዕጣ ቁጥር፦ {prev_lottery}"
        )
        bot.send_message(chat_id, duplicate_msg, parse_mode="HTML")
        user_state.pop(chat_id, None)
        return

    if came_from_photo and full_name:
        # OCR found both ID and name — go straight to mobile
        user_state[chat_id] = {
            "step": "awaiting_mobile",
            "record_id": record["id"],
            "full_name": full_name,
        }
        bot.send_message(chat_id, "እባክዎ ስልክ ቁጥርዎን ያስገቡ (ቁጥር ብቻ)")
    elif came_from_photo and not full_name:
        # OCR found the ID but could not read the name — ask user to type it
        user_state[chat_id] = {
            "step": "awaiting_name",
            "record_id": record["id"],
            "full_name": None,
        }
        bot.send_message(
            chat_id,
            "ይቅርታ፣ ስምዎን ከፎቶው ላይ ማንበብ አልቻልኩም። እባክዎ ሙሉ ስምዎን እዚህ ይጻፉልኝ?",
        )
    else:
        # Manual entry — ask for name next
        user_state[chat_id] = {
            "step": "awaiting_name",
            "record_id": record["id"],
            "full_name": None,
        }
        bot.send_message(chat_id, "እባክዎ ሙሉ ስምዎን ያስገቡ")


# ---------------------------------------------------------------------------
# Telegram handlers
# ---------------------------------------------------------------------------

@bot.message_handler(commands=["start"])
def handle_start(message: telebot.types.Message) -> None:
    user_state[message.chat.id] = {
        "step": "awaiting_transaction",
        "record_id": None,
        "full_name": None,
    }
    bot.send_message(
        message.chat.id,
        "እንኳን ደህና መጡ! 🎉\n"
        "\n"
        "እባክዎ የባንክ ደረሰኝ ፎቶ (Screenshot) ይላኩ ወይም የ Transaction ID ቁጥሩን ፅፈው ያስገቡ።\n"
        "\n"
        "ℹ️ <b>ማሳሰቢያ፦</b>\n"
        "በደረሰኙ ላይ ያለውን ስም ቦቱ በቀጥታ እንዲያነብ ካልፈለጉ፣ ፎቶ አይላኩ።\n"
        "ይልቁንም የ Transaction ID ቁጥሩን ብቻ በጽሁፍ ያስገቡ — ያኔ ስምዎን በእጅ እንዲያስገቡ ይጠየቃሉ።",
        parse_mode="HTML",
    )


@bot.message_handler(content_types=["photo"])
def handle_photo(message: telebot.types.Message) -> None:
    chat_id = message.chat.id
    state = user_state.get(chat_id)

    if not state or state.get("step") != "awaiting_transaction":
        bot.send_message(chat_id, "እባክዎ 👉 /start ይጫኑ ለመጀመር።")
        return

    file_id = message.photo[-1].file_id
    try:
        file_info = bot.get_file(file_id)
        photo_bytes = bot.download_file(file_info.file_path)
    except Exception as exc:
        print(f"[PHOTO DOWNLOAD ERROR]: {exc!r}", flush=True)
        bot.send_message(chat_id, "ስህተት ተፈጥሯል፣ እባክዎ ቆይተው ይሞክሩ።")
        return

    bot.send_message(chat_id, "ፎቶውን እያነበብኩ ነው፣ እባክዎ ይጠብቁ...")
    transaction_id, customer_name = extract_data_from_image(photo_bytes)

    if not transaction_id:
        bot.send_message(
            chat_id,
            "ይቅርታ፣ ደረሰኙን ማንበብ አልቻልኩም። እባክዎ በደንብ የሚታይ ፎቶ ይላኩ "
            "ወይም የ Transaction ID ቁጥሩን በእጅ ይጻፉ።",
        )
        return

    confirmation = f"Transaction ID ተገኝቷል: {transaction_id}"
    if customer_name:
        confirmation += f"\nስም: {customer_name}"
    bot.send_message(chat_id, confirmation)

    lookup_and_advance(
        chat_id,
        transaction_id,
        full_name=customer_name,
        came_from_photo=True,
    )


@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(message: telebot.types.Message) -> None:
    chat_id = message.chat.id
    state = user_state.get(chat_id)
    text = (message.text or "").strip()

    if not state:
        bot.send_message(chat_id, "እባክዎ 👉 /start ይጫኑ ለመጀመር።")
        return

    step = state.get("step")

    # ── Step 1: Transaction ID typed manually ────────────────────────────────
    if step == "awaiting_transaction":
        lookup_and_advance(
            chat_id,
            text.upper(),
            full_name=None,
            came_from_photo=False,
        )
        return

    # ── Step 2 (manual only): Full Name ─────────────────────────────────────
    if step == "awaiting_name":
        if not text:
            bot.send_message(chat_id, "እባክዎ ሙሉ ስምዎን ያስገቡ")
            return
        state["full_name"] = text
        state["step"] = "awaiting_mobile"
        bot.send_message(chat_id, "እባክዎ ስልክ ቁጥርዎን ያስገቡ (ቁጥር ብቻ)")
        return

    # ── Step 3: Mobile number ────────────────────────────────────────────────
    if step == "awaiting_mobile":
        record_id = state.get("record_id")
        if not record_id:
            user_state.pop(chat_id, None)
            bot.send_message(chat_id, "እባክዎ 👉 /start ይጫኑ ለመጀመር።")
            return

        if not re.fullmatch(r"\d+", text):
            bot.send_message(chat_id, "⚠️ እባክህ ሞባይል ቁጥርህ ብቻ አስገባ")
            return  # loop — stay in awaiting_mobile

        full_name = state.get("full_name")
        try:
            updated = update_record(record_id, text, chat_id, full_name=full_name)
        except Exception:
            bot.send_message(chat_id, "ስህተት ተፈጥሯል፣ እባክዎ ቆይተው ይሞክሩ።")
            return

        fields = updated.get("fields", {})
        lottery_number = fields.get("Lottery number", "")

        bot.send_message(
            chat_id,
            SUCCESS_MESSAGE_TEMPLATE.format(
                lottery_number=html.escape(str(lottery_number))
            ),
            parse_mode="HTML",
            disable_web_page_preview=False,
        )
        user_state.pop(chat_id, None)
        return


# ---------------------------------------------------------------------------
# Health-check HTTP server
# ---------------------------------------------------------------------------
# Replit's publishing system requires an HTTP endpoint to validate the
# deployment before allowing publish. This tiny server satisfies that check
# without interfering with the Telegram bot in any way.

_LANDING_HTML = b"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Emunat Delala Lottery</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;
  background:linear-gradient(135deg,#0f2027,#203a43,#2c5364);
  min-height:100vh;display:flex;flex-direction:column;align-items:center;color:#fff}
header{width:100%;background:rgba(0,0,0,.35);padding:18px 32px;
  border-bottom:1px solid rgba(255,255,255,.08)}
header h1{font-size:1.4rem;font-weight:700}
.dot{display:inline-block;width:8px;height:8px;background:#4caf50;
  border-radius:50%;margin-right:6px}
.status{font-size:.85rem;color:#ffd700;font-weight:600;margin-top:4px}
.hero{text-align:center;padding:60px 24px 40px;max-width:680px;width:100%}
.badge{display:inline-block;background:#ffd700;color:#1a1a1a;font-weight:700;
  font-size:.78rem;padding:4px 14px;border-radius:20px;letter-spacing:1px;
  text-transform:uppercase;margin-bottom:20px}
h2{font-size:2.4rem;font-weight:800;line-height:1.2;margin-bottom:16px}
h2 span{color:#ffd700}
.desc{font-size:1.05rem;color:rgba(255,255,255,.75);line-height:1.7;margin-bottom:32px}
.draw-box{background:rgba(255,215,0,.12);border:1px solid rgba(255,215,0,.35);
  border-radius:12px;padding:16px 28px;display:inline-block;margin-bottom:36px}
.draw-label{font-size:.78rem;color:#ffd700;text-transform:uppercase;letter-spacing:1px}
.draw-date{font-size:1.5rem;font-weight:800;margin-top:4px}
.tg-btn{display:inline-flex;align-items:center;gap:10px;background:#229ED9;
  color:#fff;font-size:1.05rem;font-weight:700;padding:16px 36px;border-radius:50px;
  text-decoration:none;box-shadow:0 4px 24px rgba(34,158,217,.45)}
.steps{width:100%;max-width:820px;padding:0 24px 60px;
  display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px}
.step{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);
  border-radius:16px;padding:28px 24px;text-align:center}
.step-icon{font-size:2rem;margin-bottom:14px}
.step-title{font-size:1rem;font-weight:700;color:#ffd700;margin-bottom:8px}
.step-desc{font-size:.88rem;color:rgba(255,255,255,.65);line-height:1.6}
.socials{display:flex;gap:16px;justify-content:center;padding:0 24px 48px;flex-wrap:wrap}
.social-link{display:inline-flex;align-items:center;gap:8px;
  background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);
  color:#fff;text-decoration:none;padding:10px 20px;border-radius:50px;
  font-size:.88rem;font-weight:600}
footer{width:100%;text-align:center;padding:20px;font-size:.8rem;
  color:rgba(255,255,255,.35);border-top:1px solid rgba(255,255,255,.08)}
</style>
</head>
<body>
<header>
  <h1>Emunat Delala Lottery</h1>
  <div class="status"><span class="dot"></span>Bot Online &amp; Accepting Registrations</div>
</header>
<div class="hero">
  <div class="badge">Official Registration</div>
  <h2>Register for the<br><span>Lucky Draw</span></h2>
  <p class="desc">Participate in the Emunat Delala Lottery by sending your CBE Mobile Banking
  receipt photo to our Telegram bot. Your Transaction ID is verified instantly and you receive
  your lottery number right away.</p>
  <div class="draw-box">
    <div class="draw-label">Draw Date</div>
    <div class="draw-date">&#4661;&#4637; 5 / 2018 E.C.</div>
  </div><br>
  <a class="tg-btn" href="https://t.me/emunat_lottery_bot" target="_blank" rel="noopener">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="#fff">
      <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562
      8.247-1.97 9.289c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053
      5.56-5.023c.242-.213-.054-.333-.373-.12l-6.871 4.326-2.962-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194
      1.006.131.833.932z"/>
    </svg>
    Register via Telegram Bot
  </a>
</div>
<div class="steps">
  <div class="step"><div class="step-icon">&#128248;</div>
    <div class="step-title">Step 1 &mdash; Send Receipt</div>
    <div class="step-desc">Open the bot and send a photo of your CBE Mobile Banking payment receipt,
    or type your Transaction ID manually.</div></div>
  <div class="step"><div class="step-icon">&#9989;</div>
    <div class="step-title">Step 2 &mdash; Verify</div>
    <div class="step-desc">The bot reads your Transaction ID automatically using OCR and checks it
    against our verified payment records.</div></div>
  <div class="step"><div class="step-icon">&#127967;</div>
    <div class="step-title">Step 3 &mdash; Get Your Number</div>
    <div class="step-desc">Once confirmed, your name and mobile number are saved and you instantly
    receive your unique lottery number.</div></div>
  <div class="step"><div class="step-icon">&#128250;</div>
    <div class="step-title">Step 4 &mdash; Watch the Draw</div>
    <div class="step-desc">Follow our Facebook, YouTube, or TikTok on draw day &mdash;
    &#4661;&#4637; 5/2018 &mdash; to see if your number wins!</div></div>
</div>
<div class="socials">
  <a class="social-link" href="https://www.facebook.com/share/18335v162t/" target="_blank" rel="noopener">&#128280; Facebook</a>
  <a class="social-link" href="https://youtube.com/@emunatdelala" target="_blank" rel="noopener">&#9654;&#65039; YouTube</a>
  <a class="social-link" href="https://www.tiktok.com/@emunat.com" target="_blank" rel="noopener">&#127925; TikTok</a>
</div>
<footer>&copy; 2024 Emunat Delala Lottery &mdash; All rights reserved</footer>
</body>
</html>"""


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/healthz", "/api/healthz"):
            body = b"OK"
            content_type = "text/plain"
        else:
            body = _LANDING_HTML
            content_type = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass  # silence default access logs


class _ReuseAddrHTTPServer(HTTPServer):
    """HTTPServer with SO_REUSEADDR set before bind so restarts don't fail."""
    allow_reuse_address = True


def _start_health_server() -> None:
    port = int(os.environ.get("BOT_PORT", 8082))
    try:
        server = _ReuseAddrHTTPServer(("0.0.0.0", port), _HealthHandler)
    except OSError:
        # Port already bound (e.g. second call after a bot restart) — the
        # existing server thread is still serving, nothing to do.
        logger.debug("Health server port %d already in use — keeping existing server", port)
        return
    logger.info("Health-check server listening on port %d", port)
    server.serve_forever()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Start the health-check server in a daemon thread so it exits cleanly
    # when the main process stops.
    health_thread = threading.Thread(target=_start_health_server, daemon=True)
    health_thread.start()

    logger.info("Bot is running. Press Ctrl+C to stop.")
    bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    main()
