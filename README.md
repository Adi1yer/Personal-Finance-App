# Personal Finance

Local-first personal finance for Mac: bank sync (Plaid), Google Drive backups, goals, and a **local AI advisor** (Ollama). Your ledger stays on your machine.

## Who this is for

Anyone who wants a private desktop finance app. Bring your own free Plaid and Google Cloud credentials. Works with any Plaid-supported bank — not Chase-only.

## Quick start

```bash
git clone https://github.com/Adi1yer/Personal-Finance-App.git
cd Personal-Finance-App
make setup
make launch
```

Or build a one-click Mac app: `make mac-app` → open **Applications → Personal Finance**.

1. Create an account in the app (email + password).
2. **Settings → Connections setup** — paste Plaid + Google OAuth keys (see [docs/SETUP.md](docs/SETUP.md) or in-app **Setup help**).
3. **Connect bank** → map accounts → sync.
4. Optional: connect Google Drive backups; install [Ollama](https://ollama.com) for the Advisor.
5. Manual 401(k)/HSA: set balances + **Total contributions**; configure **Goals**.

## Features

- Multi-profile local ledgers (`data/profiles/<id>/ledger.db`)
- Plaid transactions + investments sync
- Manual 401(k) / HSA balances + contribution tracking
- Annual investing % and safety-net goals
- Google Drive snapshot backups (keep last 5)
- Local Advisor (Ollama) for finances **and** setup help (reads `docs/help/`)

## Docs

| Doc | Topic |
|-----|--------|
| **[docs/help/](docs/help/README.md)** | Full setup walkthrough (what to expect / click) |
| [docs/SETUP.md](docs/SETUP.md) | Short Plaid / Google / Ollama checklist |
| [docs/SECURITY.md](docs/SECURITY.md) | What stays local, what not to commit |
| [docs/ACCOUNTS_AND_PLAID.md](docs/ACCOUNTS_AND_PLAID.md) | Accounts + Plaid (Chase as an example) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design |

## Developer commands

| Command | Purpose |
|---------|---------|
| `make setup` | Python + frontend install |
| `make launch` | API + UI + desktop wrapper |
| `make dev-api` | API with hot reload |
| `make trust-cert` | Local HTTPS for OAuth banks |
| `make test` | Backend tests |

## Privacy

Secrets live in `.env` and/or `data/app_config.json` (gitignored). Never commit `.env`, `data/`, or real API keys.
