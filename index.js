/**
   * Awche Lottery Telegram Bot
   * --------------------------
   * The bot itself runs in Python: `python main.py`
   *
   * This file provides a simple Node.js info server that can be used
   * to verify the project is wired correctly or as a standalone info endpoint.
   *
   * Usage:  node index.js
   */

  const http = require("http");
  const os = require("os");

  const PORT = process.env.PORT || 3000;

  const HTML = `<!DOCTYPE html>
  <html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Awche Lottery Bot</title>
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body {
        font-family: 'Segoe UI', sans-serif;
        background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #fff;
      }
      .card {
        background: rgba(255,255,255,0.07);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 20px;
        padding: 48px 40px;
        text-align: center;
        max-width: 480px;
        width: 90%;
      }
      h1 { font-size: 1.8rem; font-weight: 800; margin-bottom: 8px; }
      .gold { color: #ffd700; }
      p { color: rgba(255,255,255,0.72); line-height: 1.7; margin: 16px 0; }
      a.btn {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: #229ED9;
        color: #fff;
        text-decoration: none;
        padding: 12px 28px;
        border-radius: 50px;
        font-weight: 700;
        font-size: 0.95rem;
        margin-top: 8px;
      }
      .status { font-size: 0.8rem; color: rgba(255,255,255,0.4); margin-top: 24px; }
      .dot { display: inline-block; width: 8px; height: 8px; background: #4caf50; border-radius: 50%; margin-right: 5px; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1>&#127881; <span class="gold">Awche Lottery</span></h1>
      <p>Register for the lucky draw by sending your CBE Mobile Banking receipt to our Telegram bot.</p>
      <a class="btn" href="https://t.me/+hNcPdZTTL-xhMjhk" target="_blank" rel="noopener">
        &#9992;&#65039; Join on Telegram
      </a>
      <div class="status">
        <span class="dot"></span>Bot is running &mdash; Node ${process.version} &mdash; ${os.platform()}
      </div>
    </div>
  </body>
  </html>`;

  const server = http.createServer((req, res) => {
    if (req.url === "/healthz" || req.url === "/api/healthz") {
      res.writeHead(200, { "Content-Type": "text/plain" });
      return res.end("OK");
    }
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(HTML);
  });

  server.listen(PORT, "0.0.0.0", () => {
    console.log(`[Awche Lottery] Info server running on http://0.0.0.0:${PORT}`);
    console.log("Bot runtime: Python — run `python main.py` to start the Telegram bot.");
  });
  