"""
Minimal HTTP health server for the api-server slot in production.
The Express server is not needed in production (the bot talks directly
to Telegram and Airtable). This tiny server keeps port 8080 alive so
the Replit proxy health-check does not time out.
"""
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"[minimal_health] listening on 0.0.0.0:{port}", flush=True)
    HTTPServer(("0.0.0.0", port), _Handler).serve_forever()
