# Cloud backend (always-on Plaid sync)

Your **Mac app becomes the tagging UI**. The **cloud server** holds data and runs Plaid sync on a schedule—even when your laptop is off.

```
Plaid (Chase) ──► Cloud API (always on) ──► SQLite/Postgres data volume
                        ▲
                        │ HTTPS + login
                  Mac desktop app (tag expenses/income)
```

## 1. Deploy the cloud API

### Option A — Docker on a VPS (Railway, Fly.io, DigitalOcean, etc.)

1. Copy this repo to the server (or build image in CI).
2. Set `.env` on the server with production Plaid keys and:
   ```env
   PLAID_ENV=production
   PLAID_ENABLED=true
   CLOUD_SCHEDULER_ENABLED=true
   API_HOST=0.0.0.0
   CORS_ORIGINS=http://127.0.0.1:8000
   ```
3. Build and run:
   ```bash
   make cloud-build
   docker compose up -d
   ```
4. Put **HTTPS** in front (Caddy, nginx, or your host’s TLS). Note the public URL, e.g. `https://finance.yourdomain.com`.

The scheduler runs **daily at 06:00 UTC** and syncs any profile whose transactions are older than 7 days or holdings older than 30 days.

### Option B — Run without Docker

```bash
CLOUD_SCHEDULER_ENABLED=true API_HOST=0.0.0.0 ./scripts/run-cloud.sh
```

Use a process manager (systemd, supervisord) so it restarts on reboot.

## 2. Move your data to the cloud (one time)

Copy your local `data/` folder to the server volume:

```bash
rsync -avz data/ user@your-server:/path/to/personal_finance_repo/data/
```

Or register a new account on the cloud server and connect Plaid fresh.

## 3. Point the Mac app at the cloud

Set before launching (or in `~/Applications/Personal Finance.app` launch script):

```bash
export PERSONAL_FINANCE_API_URL=https://finance.yourdomain.com
```

Then open Personal Finance. The app serves UI locally but **all API calls** (login, accounts, sync status, tagging) go to the cloud.

Rebuild the Mac app after pulling updates:

```bash
make build-ui mac-app
```

## 4. Connect Chase on the cloud

1. Open the app (signed in to cloud).
2. **Settings → Connect bank** → Chase.
3. Map accounts and tap **Sync now** once.
4. After that, the **cloud scheduler** keeps transactions weekly and holdings monthly.

## 5. Your workflow

| Task | Where |
|------|--------|
| Automatic Plaid refresh | Cloud server (daily check, 7d/30d rules) |
| Tag/categorize transactions | Mac app |
| Manual 401(k) / HSA marks | Mac app → Accounts |

## Manual sync on the server

```bash
make cloud-sync
# or force full sync:
.venv/bin/finance sync-all-profiles --force
```

## Security notes

- Use **HTTPS** in production.
- Set `CORS_ORIGINS` to your desktop origin (`http://127.0.0.1:8000` for the local UI shell).
- Never commit `.env`; rotate keys if exposed.