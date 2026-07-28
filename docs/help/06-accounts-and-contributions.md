# 6. Accounts & contributions

## Chart of accounts

**Accounts** is your local chart of accounts. Every dollar lives on an account here, whether it came from Plaid or you typed it.

### Add an account

1. **Accounts → Add account**
2. Name it clearly (e.g. “Chase Checking”, “Fidelity Roth”, “Fidelity 401(k)”).
3. Choose type:
   - **depository** — checking / savings
   - **credit** — credit cards
   - **investment** — brokerage, IRA, 401(k), HSA, etc.
4. Pick a matching **subtype** (checking, credit_card, brokerage, retirement, hsa, …).

### Update balance (manual accounts)

For accounts Plaid does not sync:

1. Open the account
2. **Update balance** with the current total from your provider’s website/app
3. Optionally set a note / as-of date

Do this periodically (e.g. monthly) so Goals and net worth stay honest.

## Total contributions (YTD)

Used by the **investing goal** so workplace accounts without downloadable contribution transactions still count.

1. Open a retirement / HSA / brokerage account
2. Find **Total contributions** (year-to-date)
3. Enter the **full YTD total** from your plan site (not “add another $500”)
4. Save

### Who should fill this in?

| Account | What to do |
|---------|------------|
| Plaid-linked brokerage / IRA with deposits syncing | Usually leave blank — the app detects contributions from transactions |
| Manual 401(k) | Enter YTD employee + employer contributions from the plan portal |
| Manual HSA | Enter YTD contributions from the HSA provider |
| Mixed | Prefer transaction detection when Sync works; use Total contributions when it doesn’t |

### What you should see on Goals

After saving, **Goals → Investing** should list that account in the breakdown with the contribution amount.

## Tracking start date

Optional per-account date: ignore older history when syncing. Leave blank for “import everything Plaid sends.”

## Institution quirks (example: Chase)

Some banks map cash-sweep / ACH transfers oddly in Plaid. The app includes a Chase-aware detector so large deposit-sweep ACH into brokerage can count as investing contributions. Other banks use the generic rules (contribution / match / deposit / transfer-in).

Next: [Annual goals](07-goals.md)
