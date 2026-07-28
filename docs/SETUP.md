# Setup guide (bring your own keys)

This app is **local-first**. You create free developer accounts at Plaid and Google, paste the keys into **Settings → Connections setup**, and keep them on your Mac only.

## 1. Encryption key

On first save in Connections setup, the app can generate an `ENCRYPTION_KEY` automatically (stored in `data/app_config.json`). You can also put one in `.env`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 2. Plaid (bank sync)

1. Sign up at [dashboard.plaid.com](https://dashboard.plaid.com/).
2. Copy **client_id** and **secret** (start with **Sandbox**).
3. Enable products: **Transactions**, **Investments** (and **Auth** if offered).
4. Under Team Settings → API → **Allowed redirect URIs**, add the URI shown in the app (typically):
   - Sandbox: `http://127.0.0.1:8000/oauth/plaid.html`
   - Production: `https://127.0.0.1:8000/oauth/plaid.html` (needs local TLS — see below)
5. In the app: **Settings → Connections setup** → paste keys → set environment → Save.
6. **Settings → Connect bank** → complete Link in your browser → map accounts → Sync.

Production / OAuth banks (e.g. Chase) often require HTTPS. On Mac:

```bash
brew install mkcert
make trust-cert
```

Then restart the app. If the browser warns about the local certificate, proceed for localhost only.

## 3. Google Drive backups

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable **Google Drive API**.
3. Configure the **OAuth consent screen** (External / Testing is fine for personal use).
4. Add yourself under **Audience → Test users**.
5. Create credentials → **OAuth client ID** → type **Web application**.
6. Authorized redirect URI (must match the app exactly), e.g.:
   `https://localhost:8000/oauth/google-drive.html`
7. Paste client ID + secret in **Connections setup**.
8. **Settings → Google Drive backups → Connect**.

## 4. Ollama (local Advisor)

1. Install from [ollama.com](https://ollama.com).
2. Pull a model, e.g. `ollama pull llama3.1`.
3. In **Settings → Preferences**, set URL (`http://localhost:11434`) and model name.
4. Open **Advisor** and try a setup prompt like “How do I connect my bank with Plaid?”

The rest of the app works without Ollama.

## 5. First profile

Register with email + password. Save the **recovery code**. Data for that login lives under `data/profiles/<uuid>/ledger.db`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Plaid “not configured” | Save keys in Connections setup; ensure encryption key exists |
| OAuth redirect mismatch | Copy the URI from Settings exactly into Plaid / Google |
| Safari “connection not private” | Expected for local HTTPS — Show Details → visit website |
| Drive 403 access_denied | Add your Gmail as an OAuth **test user** |
| Advisor offline | Start Ollama; check URL/model in Settings |
