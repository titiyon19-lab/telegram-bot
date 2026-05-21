"""
Telegram Lottery Bot — Awche Lottery  (Production / Railway)
-------------------------------------------------------------
Flow:
  /start → instant welcome (first name) + ask Transaction ID
  text   → exact Airtable FT lookup  → ask Full Name + City
  text   → store name+city           → ask Mobile number
  text   → Airtable save             → success + lottery number

Architecture:
  • Telegram polling loop — never blocked, sub-ms handler returns
  • _TEXT_POOL  (6 workers) — fast Airtable lookups (FT ID queries)
  • _SAVE_POOL  (4 workers) — Airtable registration writes
  • Health HTTP server on $PORT — Railway health-check compatible
  • SIGTERM handler — graceful shutdown
  • Polling reconnect loop — auto-restarts after transient failures

Target latency:
  /start     < 200 ms  (pure in-handler, no I/O)
  FT lookup  < 2 s     (Airtable query in _TEXT_POOL thread)

Required env vars:
  TELEGRAM_BOT_TOKEN   BotFather token
  AIRTABLE_API_KEY     Personal access token
  AIRTABLE_BASE_ID     (default: appa4GoH54MAPKcUT)
  AIRTABLE_TABLE_NAME  (default: tblqr6cf0PQA5Zwel)
  PORT                 HTTP health-check port (Railway injects this)
"""

from __future__ import annotations

import html
import logging
import os
import re
import signal
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

import telebot
from pyairtable import Api
from pyairtable.formulas import match

# ─────────────────────────────────────────────────────────────────────────────
# Structured logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("awche_bot")

# ─────────────────────────────────────────────────────────────────────────────
# Environment & token validation  (fail fast)
# ─────────────────────────────────────────────────────────────────────────────

def _require_env(key: str, default: str = "") -> str:
    val = os.environ.get(key, default).strip()
    if not val and not default:
        raise SystemExit(f"[FATAL] Missing required env var: {key}")
    return val

_raw_token = _require_env("TELEGRAM_BOT_TOKEN")
if ":" not in _raw_token or not _raw_token.split(":")[0].isdigit():
    raise SystemExit("[FATAL] TELEGRAM_BOT_TOKEN format invalid — re-paste from BotFather.")
_bot_id = _raw_token.split(":")[0]
log.info("[BOOT] Token OK — bot_id=%s suffix=...%s", _bot_id, _raw_token[-6:])

AIRTABLE_API_KEY    = _require_env("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID    = _require_env("AIRTABLE_BASE_ID",    "appa4GoH54MAPKcUT")
AIRTABLE_TABLE_NAME = _require_env("AIRTABLE_TABLE_NAME", "tblqr6cf0PQA5Zwel")
HEALTH_PORT         = int(os.environ.get("PORT", os.environ.get("BOT_PORT", "8080")))

# ─────────────────────────────────────────────────────────────────────────────
# Thread pools  (separate to prevent text lookups starving saves or vice-versa)
# ─────────────────────────────────────────────────────────────────────────────

_TEXT_POOL = ThreadPoolExecutor(max_workers=6,  thread_name_prefix="text")
_SAVE_POOL = ThreadPoolExecutor(max_workers=4,  thread_name_prefix="save")

def _run_in(pool: ThreadPoolExecutor, fn, *args) -> None:
    """Submit fn(*args) to pool. Handler returns instantly."""
    pool.submit(fn, *args)

# ─────────────────────────────────────────────────────────────────────────────
# Clients
# ─────────────────────────────────────────────────────────────────────────────

bot      = telebot.TeleBot(_raw_token, threaded=True, num_threads=12)
airtable = Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)

# ─────────────────────────────────────────────────────────────────────────────
# Airtable warmup  (verify connectivity at startup, not mid-request)
# ─────────────────────────────────────────────────────────────────────────────

def _warmup_airtable() -> None:
    t0 = time.monotonic()
    try:
        airtable.all(max_records=1)
        log.info("[BOOT] Airtable connection OK  (%.2fs)", time.monotonic() - t0)
    except Exception as exc:
        log.warning("[BOOT] Airtable warmup failed (non-fatal): %s", exc)

# ─────────────────────────────────────────────────────────────────────────────
# Conversation state   {chat_id: {"step", "record_id", "full_name"}}
# Steps: awaiting_transaction → awaiting_name_city → awaiting_mobile
# ─────────────────────────────────────────────────────────────────────────────

_state_lock: threading.Lock = threading.Lock()
_state: dict[int, dict]     = {}

def _get(chat_id: int) -> Optional[dict]:
    with _state_lock:
        return _state.get(chat_id)

def _put(chat_id: int, s: dict) -> None:
    with _state_lock:
        _state[chat_id] = s

def _pop(chat_id: int) -> None:
    with _state_lock:
        _state.pop(chat_id, None)

# ─────────────────────────────────────────────────────────────────────────────
# Static strings
# ─────────────────────────────────────────────────────────────────────────────

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
    "Facebook:\nhttp://facebook.com/share/1DwpPzF9bQ\n"
)

# ─────────────────────────────────────────────────────────────────────────────
# Airtable helpers
# ─────────────────────────────────────────────────────────────────────────────

def _at_find(txn_id: str) -> Optional[dict]:
    """Exact match lookup by Transaction ID. Returns first record or None."""
    t0 = time.monotonic()
    records = airtable.all(formula=match({"Transaction ID": txn_id}), max_records=1)
    elapsed = time.monotonic() - t0
    found   = bool(records)
    log.info("[AIRTABLE] lookup txn=%-20s found=%-5s %.2fs", txn_id, found, elapsed)
    return records[0] if records else None


def _at_save(record_id: str, mobile: str, chat_id: int, full_name: Optional[str]) -> dict:
    fields: dict = {
        "User mobile": mobile,
        "Chat ID":     str(chat_id),
        "Status":      "Verified",
    }
    if full_name:
        fields["Full Name"] = full_name
    t0     = time.monotonic()
    result = airtable.update(record_id, fields, typecast=True)
    log.info("[AIRTABLE] save  record=%-20s %.2fs", record_id, time.monotonic() - t0)
    return result


def _already_registered(fields: dict) -> bool:
    return bool(str(fields.get("Chat ID", "") or "").strip())

# ─────────────────────────────────────────────────────────────────────────────
# Worker functions  (run inside thread pools, never in handlers)
# ─────────────────────────────────────────────────────────────────────────────

def _worker_lookup(chat_id: int, txn_id: str) -> None:
    """FT ID lookup worker — runs in _TEXT_POOL."""
    try:
        record = _at_find(txn_id)
    except Exception as exc:
        log.error("[ERROR] Airtable lookup chat=%s txn=%s: %s", chat_id, txn_id, exc)
        traceback.print_exc()
        bot.send_message(chat_id, "ስህተት ተፈጥሯል፣ እባክዎ ቆይተው ይሞክሩ።")
        return

    if not record:
        bot.send_message(
            chat_id,
            "ይቅርታ፣ ይህ Transaction ID አልተገኘም።\n"
            "እባክዎ ትክክለኛ FT... ቁጥር ያስገቡ ወይም ቆይቶ ይሞክሩ።",
        )
        return

    fields = record.get("fields", {})
    if _already_registered(fields):
        p_name   = html.escape(str(fields.get("Full Name",      "") or "—"))
        p_mobile = html.escape(str(fields.get("User mobile",    "") or "—"))
        p_lotto  = html.escape(str(fields.get("Lottery number", "") or "—"))
        bot.send_message(
            chat_id,
            "⚠️ <b>ይህ Transaction ID ቀድሞ ተመዝግቧል!</b>\n"
            "\n"
            "የቀድሞ ምዝገባ መረጃ፦\n"
            f"ስም፦ {p_name}\n"
            f"ስልክ፦ {p_mobile}\n"
            f"የዕጣ ቁጥር፦ {p_lotto}",
            parse_mode="HTML",
        )
        _pop(chat_id)
        return

    _put(chat_id, {
        "step":      "awaiting_name_city",
        "record_id": record["id"],
        "full_name": None,
    })
    bot.send_message(chat_id, "እባክዎ ሙሉ ስምዎን እና የሚኖሩበትን ከተማ ያስገቡ።")


def _worker_save(chat_id: int, record_id: str, mobile: str, full_name: Optional[str]) -> None:
    """Registration save worker — runs in _SAVE_POOL."""
    try:
        updated = _at_save(record_id, mobile, chat_id, full_name)
    except Exception as exc:
        log.error("[ERROR] Airtable save chat=%s record=%s: %s", chat_id, record_id, exc)
        traceback.print_exc()
        bot.send_message(chat_id, "ስህተት ተፈጥሯል፣ እባክዎ ቆይተው ይሞክሩ።")
        return

    lottery_number = updated.get("fields", {}).get("Lottery number", "")
    bot.send_message(
        chat_id,
        _SUCCESS.format(lottery_number=html.escape(str(lottery_number))),
        parse_mode="HTML",
        disable_web_page_preview=False,
    )
    _pop(chat_id)

# ─────────────────────────────────────────────────────────────────────────────
# Telegram handlers  — each handler MUST return in <200 ms
# ─────────────────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def handle_start(message: telebot.types.Message) -> None:
    t0         = time.monotonic()
    chat_id    = message.chat.id
    first_name = (
        (message.from_user.first_name or "").strip()
        if message.from_user else ""
    )
    _put(chat_id, {"step": "awaiting_transaction", "record_id": None, "full_name": None})
    bot.send_message(
        chat_id,
        f"እንኳን ደህና መጡ! 🎉 {first_name}\n\n"
        "እባክዎ የባንክ Transaction ID ቁጥሩን ፅፈው ያስገቡ። FT የሚጀምር",
    )
    log.info("[START] chat=%-12s user=%-15s %.3fs", chat_id, first_name, time.monotonic() - t0)


@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(message: telebot.types.Message) -> None:
    chat_id = message.chat.id
    state   = _get(chat_id)
    text    = (message.text or "").strip()

    if not state:
        bot.send_message(chat_id, _PLEASE_START)
        return

    step = state.get("step")

    # ── 1. Transaction ID → TEXT_POOL lookup (non-blocking) ──────────────────
    if step == "awaiting_transaction":
        if not text:
            bot.send_message(chat_id, "እባክዎ Transaction ID ያስገቡ (FT የሚጀምር)")
            return
        log.info("[TEXT] lookup queued  chat=%-12s txn=%s", chat_id, text.upper())
        _run_in(_TEXT_POOL, _worker_lookup, chat_id, text.upper())
        return

    # ── 2. Full name + city → pure state mutation, zero I/O ──────────────────
    if step == "awaiting_name_city":
        if not text:
            bot.send_message(chat_id, "እባክዎ ሙሉ ስምዎን እና የሚኖሩበትን ከተማ ያስገቡ።")
            return
        state["full_name"] = text
        state["step"]      = "awaiting_mobile"
        _put(chat_id, state)
        bot.send_message(chat_id, "እባክዎ ስልክ ቁጥርዎን ያስገቡ (ቁጥር ብቻ)")
        return

    # ── 3. Mobile number → SAVE_POOL write (non-blocking) ────────────────────
    if step == "awaiting_mobile":
        record_id = state.get("record_id")
        if not record_id:
            _pop(chat_id)
            bot.send_message(chat_id, _PLEASE_START)
            return
        if not re.fullmatch(r"\d{7,15}", text):
            bot.send_message(chat_id, "⚠️ ትክክለኛ ሞባይል ቁጥር ያስገቡ (ቁጥር ብቻ)")
            return
        log.info("[TEXT] save queued  chat=%-12s record=%s", chat_id, record_id)
        _run_in(_SAVE_POOL, _worker_save, chat_id, record_id, text, state.get("full_name"))
        return

    bot.send_message(chat_id, _PLEASE_START)


# Catch-all — photos, stickers, audio, video, documents, etc.
@bot.message_handler(
    content_types=[
        "photo", "sticker", "document", "audio", "video",
        "voice", "video_note", "location", "contact",
        "animation", "poll", "dice", "venue", "game",
    ]
)
def handle_unsupported(_: telebot.types.Message) -> None:
    bot.send_message(_.chat.id, _PLEASE_START)


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call: telebot.types.CallbackQuery) -> None:
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, _PLEASE_START)

# ─────────────────────────────────────────────────────────────────────────────
# Health-check HTTP server
# Railway probes GET /healthz  and  GET /
# ─────────────────────────────────────────────────────────────────────────────

_STARTED_AT  = time.time()
_HEALTH_JSON = b'{"status":"ok","service":"awche-lottery-bot"}'

_LANDING_HTML = b"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Awche Lottery Bot</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#0f2027,#2c5364);
  min-height:100vh;display:flex;flex-direction:column;align-items:center;color:#fff}
header{width:100%;background:rgba(0,0,0,.35);padding:16px 28px;
  border-bottom:1px solid rgba(255,255,255,.08);display:flex;align-items:center;gap:10px}
.dot{width:9px;height:9px;background:#4caf50;border-radius:50%;flex-shrink:0}
header h1{font-size:1.2rem;font-weight:700}
.hero{text-align:center;padding:60px 24px 32px;max-width:600px}
.badge{display:inline-block;background:#ffd700;color:#111;font-weight:700;font-size:.75rem;
  padding:4px 14px;border-radius:20px;letter-spacing:1px;text-transform:uppercase;margin-bottom:18px}
h2{font-size:2.2rem;font-weight:800;line-height:1.2;margin-bottom:14px}
h2 span{color:#ffd700}
p{color:rgba(255,255,255,.7);line-height:1.7;margin-bottom:28px}
.btn{display:inline-flex;align-items:center;gap:8px;background:#229ED9;color:#fff;
  font-size:1rem;font-weight:700;padding:14px 32px;border-radius:50px;text-decoration:none;
  box-shadow:0 4px 20px rgba(34,158,217,.4)}
footer{margin-top:auto;padding:18px;font-size:.75rem;color:rgba(255,255,255,.3);
  border-top:1px solid rgba(255,255,255,.07);width:100%;text-align:center}
</style>
</head>
<body>
<header><div class="dot"></div><h1>Awche Lottery Bot &mdash; Online</h1></header>
<div class="hero">
  <div class="badge">Official Registration</div>
  <h2>Register for the<br><span>Lucky Draw</span></h2>
  <p>Type your CBE Mobile Banking Transaction ID in our Telegram bot.
  Your payment is verified instantly and you receive your lottery number right away.</p>
  <a class="btn" href="https://t.me/+hNcPdZTTL-xhMjhk" target="_blank" rel="noopener">
    &#128172; Join on Telegram
  </a>
</div>
<footer>&copy; 2024 Awche Lottery &mdash; All rights reserved</footer>
</body>
</html>"""


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path in ("/healthz", "/health", "/api/healthz"):
            uptime = int(time.time() - _STARTED_AT)
            body   = (
                b'{"status":"ok","uptime_seconds":' + str(uptime).encode() + b"}"
            )
            ctype  = "application/json"
        elif path == "/ready":
            body, ctype = b"READY", "text/plain"
        else:
            body, ctype = _LANDING_HTML, "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # suppress per-request noise; Railway monitors stdout


class _ReuseServer(HTTPServer):
    allow_reuse_address = True


def _run_health_server() -> None:
    try:
        srv = _ReuseServer(("0.0.0.0", HEALTH_PORT), _HealthHandler)
        log.info("[BOOT] Health server on port %d", HEALTH_PORT)
        srv.serve_forever()
    except OSError:
        log.warning("[BOOT] Health server port %d already in use — skipping", HEALTH_PORT)

# ─────────────────────────────────────────────────────────────────────────────
# Graceful shutdown
# ─────────────────────────────────────────────────────────────────────────────

_shutdown_event = threading.Event()


def _handle_sigterm(*_) -> None:
    log.info("[SHUTDOWN] SIGTERM received — stopping bot cleanly")
    _shutdown_event.set()
    bot.stop_polling()
    _TEXT_POOL.shutdown(wait=False)
    _SAVE_POOL.shutdown(wait=False)
    sys.exit(0)

# ─────────────────────────────────────────────────────────────────────────────
# Entry point with reconnect loop
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT,  _handle_sigterm)

    # Start health server
    threading.Thread(target=_run_health_server, daemon=True).start()

    # Warm up Airtable connection (non-blocking — runs in text pool)
    _TEXT_POOL.submit(_warmup_airtable)

    log.info("[BOOT] Bot starting — bot_id=%s", _bot_id)

    reconnect_delay = 5  # seconds between reconnect attempts
    while not _shutdown_event.is_set():
        try:
            log.info("[POLL] Starting infinity_polling (skip_pending=True)")
            bot.infinity_polling(
                skip_pending=True,
                timeout=20,
                long_polling_timeout=20,
                logger_level=logging.WARNING,
            )
        except Exception as exc:
            if _shutdown_event.is_set():
                break
            log.error("[POLL] Polling crashed: %s — reconnecting in %ds", exc, reconnect_delay)
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 60)  # exponential back-off, cap 60s
        else:
            reconnect_delay = 5  # reset after clean exit

    log.info("[SHUTDOWN] Bot stopped.")


if __name__ == "__main__":
    main()
