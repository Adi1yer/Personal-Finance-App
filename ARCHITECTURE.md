# Architecture

## Overview

Monorepo with a **FastAPI** backend, **SQLite** ledger, **React** UI, and optional **Plaid** sync—all running locally on your Mac.

```
UI (React) → API (FastAPI) → SQLite
                ↓
            Plaid (optional)
```

## Double-entry ledger

Every transaction has two or more **entries** whose signed amounts sum to zero.

| Event | Debit (increase asset / expense) | Credit |
|-------|----------------------------------|--------|
| Card purchase (accrual) | Expense | Credit card liability |
| Pay card from checking | Credit card liability | Checking (asset) |
| Salary deposit | Checking | Income |
| Transfer checking → brokerage | Brokerage | Checking |

**Transfers** set `transaction.is_transfer = true` so income-statement rollups exclude them.

## Account types

- **Balance sheet:** `asset`, `liability`, `equity`
- **P&L:** `income`, `expense`

Investment and retirement balances may use **account marks** (quarter-end market value) when transaction-level detail is incomplete.

## Accrual credit cards

Expenses are recognized when **charged** on the card, not when the checking account pays the statement. Card payments reduce liability and cash—classified as **financing** on the cash flow statement.

## Reports

| Report | Source |
|--------|--------|
| Balance sheet | Asset/liability/equity balances at `as_of`; investments use latest `account_mark` on or before date |
| Income statement | Sum income/expense accounts in period; exclude transfers |
| Cash flow | Entries on cash/checking and classified categories via `cash_flow_mapping` |

Quarters: Q1 Jan–Mar, Q2 Apr–Jun, Q3 Jul–Sep, Q4 Oct–Dec.

## Plaid pipeline

1. Link → `public_token` → encrypted `access_token` on `plaid_item`
2. Sync → `import_staging` (raw rows)
3. Dedupe by `external_id` → posting service → `transaction` + `entries`

Manual investment accounts skip Plaid; use registers and **Update balance** / `account_mark`, plus **Total contributions** for goals.

## Security

- Local-first multi-profile app; API binds to localhost by default
- Plaid / Google tokens encrypted with `ENCRYPTION_KEY` (Fernet)
- Never commit `.env`, `data/`, or `data/app_config.json`
- See [docs/SECURITY.md](docs/SECURITY.md)
