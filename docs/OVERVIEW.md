# Overview (Empower-style layout)

The **Overview** page (`/`) shows net worth, grouped accounts, and monthly widgets.

## Layout

| Column | Content |
|--------|---------|
| Left tree | Net worth, account groups, balances, “updated ago” |
| Center | Selected account detail **or** quarterly summary stats |
| Right rail | Connect bank, Sync, Add account (wide screens) |
| Bottom row | Cash flow, Spending, Emergency fund (current month) |

Select an account in the tree to see its balance and links to **Register** / **Reconcile**.

## Account grouping (subtype → group)

| Group | Subtypes |
|-------|----------|
| Cash | `checking` |
| Investments | `brokerage` |
| Retirement | `retirement` |
| Health savings | `hsa` |
| Credit cards | `credit_card` |
| Other assets | asset + `other` |
| Other liabilities | liability + `other` |

Set the correct subtype when adding or editing an account under **Accounts**.

## “Updated ago” labels

| Source | Meaning |
|--------|---------|
| Plaid account | Time since last **Sync transactions** |
| Manual + balance mark | Date of latest **Update balance** |
| Other manual | Account last modified |

## Plaid sync

- **Settings → Sync transactions** or **Overview → Sync** (right rail)
- On first open each session, auto-sync runs once if Plaid is configured and accounts are mapped

## API

- `GET /api/v1/overview` — grouped accounts + net worth
- `GET /api/v1/reports/metrics/monthly?year=&month=` — cash flow widgets

Data lives in `data/profiles/<profile-id>/ledger.db` per signed-in profile.
