"""
Production entry point for Reserved VM deployment.

The health server starts on 0.0.0.0:PORT *before* any bot code is imported,
so the GCE health probe always gets an immediate HTTP 200 regardless of
whether the bot token/secrets are present or the bot crashes.

The bot then runs in a retry loop:
  - 409 Conflict   → 60 s wait (lets the previous polling session expire)
  - Any other crash → exponential back-off (5 s .. 30 s)
"""
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [main] %(levelname)s %(message)s",
)
log = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Minimal health server — starts BEFORE the bot is imported
# ---------------------------------------------------------------------------

HEALTH_PAGE = b"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Emunat Delala Lottery Bot</title></head>
<body style="font-family:sans-serif;text-align:center;padding:60px">
<h1>&#127881; Emunat Delala Lottery</h1>
<p>Telegram lottery bot is running 24/7.</p>
<p><a href="https://t.me/EmunatLotteryBot">Open in Telegram</a></p>
</body>
</html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/healthz", "/api/healthz"):
            body = b"OK"
        else:
            body = HEALTH_PAGE
        self.send_response(200)
        self.send_header("Content-Type",
                         "text/plain" if body == b"OK" else "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # silence per-request logs
        pass


def _start_health_server(port: int) -> None:
    try:
        server = HTTPServer(("0.0.0.0", port), _Handler)
        log.info("Health server listening on 0.0.0.0:%d", port)
        server.serve_forever()
    except OSError as exc:
        log.warning("Health server could not bind to port %d: %s", port, exc)


# ---------------------------------------------------------------------------
# Bot runner
# ---------------------------------------------------------------------------

def run() -> None:
    port = int(os.environ.get("PORT", "24816"))
    os.environ["BOT_PORT"] = str(port)

    # Start health server in a daemon thread RIGHT NOW — before any bot import
    t = threading.Thread(target=_start_health_server, args=(port,), daemon=True)
    t.start()

    attempt = 0
    while True:
        attempt += 1
        log.info("Starting Telegram bot (attempt %d) …", attempt)
        try:
            # Import inside the loop so a restart re-executes module-level setup
            from telegram_lottery_bot import main as bot_main  # type: ignore[import]
            bot_main()
            log.warning("Bot stopped cleanly — restarting in 5 s …")
            time.sleep(5)
        except Exception as exc:
            err = str(exc)
            if "409" in err or "Conflict" in err:
                wait = 60
                log.warning(
                    "409 Conflict — another instance is polling. "
                    "Waiting %d s before retrying …", wait,
                )
            else:
                wait = min(30, 5 * attempt)
                log.error("Bot crashed: %s — retrying in %d s …", exc, wait)
            time.sleep(wait)


if __name__ == "__main__":
    run()
