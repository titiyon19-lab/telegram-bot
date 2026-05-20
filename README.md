# Awche Lottery Telegram Bot

  A Telegram bot for lottery registration with CBE Mobile Banking receipt OCR.

  ## Features
  - Validates Transaction IDs against Airtable
  - OCR on CBE Mobile Banking receipts (Tesseract)
  - Collects Full Name and mobile number
  - Updates Airtable with registration data
  - 24/7 health server for deployment health checks

  ## Environment Variables
  - `TELEGRAM_BOT_TOKEN` — Token from @BotFather
  - `AIRTABLE_API_KEY` — Airtable personal access token
  - `AIRTABLE_BASE_ID` — Defaults to `appa4GoH54MAPKcUT`
  - `AIRTABLE_TABLE_NAME` — Defaults to `tblqr6cf0PQA5Zwel`

  ## Run
  ```bash
  pip install -r requirements.txt
  python main.py
  ```

  ## Deployment
  Uses `nixpacks.toml` for Railway/Replit deployment with Python 3.12 and Tesseract.

  Branding: **Awche Lottery**
  