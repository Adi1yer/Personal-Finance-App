# Accounts & Plaid

How ledger accounts relate to Plaid. For first-time key setup, see [SETUP.md](SETUP.md).

## Model

| Piece | This app |
|-------|----------|
| **Ledger accounts** | **Accounts** page — you add & rename |
| **Bank aggregator** | Bring your own Plaid keys (Sandbox free; Production needs Plaid approval) |
| **Connect flow** | **Settings → Connect bank** → system browser (needed for many OAuth banks) |
| **Mapping** | **Settings → Map accounts** |
| **Sync** | **Sync now** (Settings) |
| **Manual** | Balance marks (401k, HSA) + **Total contributions** for goals |

We do **not** ship your bank names in code. Setup only creates **system** accounts (e.g. uncategorized expense). You name checking, cards, and investments yourself.

## Workflow

### 1. Name your accounts

1. **Accounts → Add account**
2. Enter your name and type (Checking, Credit card, Brokerage, Retirement, HSA, …)

### 2. Connect Plaid (Sandbox first)

Prefer **Settings → Connections setup** to paste keys (or `.env` — see [SETUP.md](SETUP.md)).

1. Get Sandbox keys from the Plaid Dashboard  
2. Ensure an encryption key exists  
3. **Connect bank** → Sandbox test institution → map accounts → **Sync**

### 3. Production / OAuth banks (example: Chase)

Many US banks require OAuth + HTTPS redirect URIs:

- Plaid Production keys + `PLAID_ENV=production`
- Allow `https://127.0.0.1:8000/oauth/plaid.html` in the Plaid Dashboard  
- Enable OAuth institutions / Data Transparency as Plaid requires  
- `make trust-cert` for local HTTPS; quit and reopen the app  
- Connect bank opens your system browser  

Chase-specific contribution detection (BANKLINK / deposit-sweep ACH) is one **institution adapter**. Other brokers that send Plaid `contribution` / `deposit` subtypes work via the generic detector.

### 4. Accounts Plaid won’t cover

Workplace 401(k), HSA, etc.: add manual asset accounts, **Update balance**, and enter **Total contributions** YTD for investing goals.

## Data storage

- Bank credentials: **never** stored — only Plaid tokens (encrypted in SQLite)
- Everything local: `data/profiles/<profile-id>/ledger.db` per profile
