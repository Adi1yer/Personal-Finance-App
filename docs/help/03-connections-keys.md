# 3. Connections setup (bring your own keys)

Open **Settings → Connections setup**.

This screen stores secrets only on your Mac (`data/app_config.json`, gitignored). You can also use a `.env` file; the UI is easier for new users.

## 3a. Encryption key

1. If status shows encryption **needed**, click **Generate encryption key** (or Save once with generate enabled).
2. Status should show encryption **ready**.

**Why:** Plaid and Google tokens are encrypted at rest with this key.

## 3b. Plaid keys (bank sync)

1. Create an account at [dashboard.plaid.com](https://dashboard.plaid.com/).
2. Open **Developers → Keys**.
3. Copy **client_id** and **secret** for **Sandbox** first.
4. Enable products: **Transactions**, **Investments** (Auth if available).
5. Team Settings → API → **Allowed redirect URIs** — add the exact URI shown under Connections setup (often `http://127.0.0.1:8000/oauth/plaid.html` for sandbox).
6. In the app:
   - Paste client ID and secret
   - Environment: **sandbox**
   - Click **Save connections**
7. Status should show Plaid **configured (sandbox)**.

### Moving to production later

- Switch environment to **production**, paste production secret, save.
- Redirect URI often becomes `https://127.0.0.1:8000/oauth/plaid.html`.
- Run `brew install mkcert && make trust-cert`, then quit and reopen the app.
- Complete Plaid Production onboarding (Data Transparency, OAuth institutions) as Plaid requires.

## 3c. Google OAuth (Drive backups)

1. Open [Google Cloud Console](https://console.cloud.google.com/) → create a project (any name).
2. **APIs & Services → Library** → enable **Google Drive API**.
3. **Google Auth Platform / OAuth consent screen**:
   - User type **External**
   - Publishing status **Testing** is fine for personal use
4. **Audience → Test users → Add users** — add the Gmail you’ll sign in with.
5. **Clients → Create client**:
   - Application type: **Web application** (not Desktop — Desktop has no redirect URI field)
   - Authorized redirect URI: copy exactly from Connections setup (often `https://localhost:8000/oauth/google-drive.html`)
6. Copy client ID + secret into Connections setup → **Save**.
7. Status should show Google Drive **configured**.

## What “configured” means

Configured ≠ connected. Next you still:

- Link a bank under **Connect bank**
- Click **Connect Google Drive** under Drive backups

Next: [Connect your bank (Plaid)](04-plaid-bank-connect.md)
