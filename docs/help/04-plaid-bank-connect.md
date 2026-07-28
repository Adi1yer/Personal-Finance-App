# 4. Connect your bank (Plaid)

Prerequisites: Plaid shows **configured** in Connections setup ([guide](03-connections-keys.md)).

## 4a. Create ledger accounts (recommended first)

1. Open **Accounts → Add account**.
2. Create the accounts you care about (names are yours), for example:
   - Checking
   - Credit card(s)
   - Brokerage
   - Roth IRA / IRA
   - 401(k) (manual if Plaid can’t link it)
   - HSA (manual if needed)
3. Pick the correct **type / subtype** (checking, credit_card, brokerage, retirement, hsa).

You can also create accounts while mapping after Link.

## 4b. Start Connect bank

1. **Settings → Connect bank (Plaid)**.
2. Click **Connect bank**.
3. Your **system browser** should open (Safari is preferred on Mac for local HTTPS).

### What you should see in the browser

1. Plaid Link UI — search your bank (Sandbox: use a Plaid test bank like “First Platypus”).
2. Complete login / MFA as your bank requires.
3. Select accounts to share.
4. When Link finishes, return to the Personal Finance app.

### Security warnings (production / HTTPS)

If you see **“This Connection Is Not Private”** for `localhost` / `127.0.0.1`:

- Safari: **Show Details → visit this website**
- Chrome/Brave: Advanced → proceed, or type `thisisunsafe` on the warning page
- Permanent fix: `make trust-cert`

This is expected for a local HTTPS cert used by OAuth banks.

## 4c. Map accounts

1. Back in Settings, Plaid status should show bank connection(s).
2. For each Plaid account, choose which **ledger account** receives downloads (or create one).
3. Save mappings.

## 4d. Sync

1. Click **Sync now**.
2. Wait for the sync summary.
3. Open **Register** / Overview — balances and transactions should appear.

### Pending vs available

Some banks show **pending** deposits in the bank app that Plaid only posts when they clear. That is not always an app bug.

## 4e. Manual accounts Plaid can’t cover

Workplace **401(k)** and some **HSAs** often can’t sync. Add them as manual accounts and update balances under **Accounts → Update balance**. See [Accounts & contributions](06-accounts-and-contributions.md).

## Common errors

| Message / symptom | Fix |
|-------------------|-----|
| Plaid not configured | Finish [Connections setup](03-connections-keys.md) |
| Redirect URI error | Add the exact URI from Settings to Plaid Dashboard |
| Browser never opens | Copy the manual link from the Settings message |
| Chase / OAuth fails | Production + HTTPS redirect + institution enabled in Plaid |
| No transactions | Confirm mapping + Sync; check tracking start on the account |

Next: [Google Drive backups](05-google-drive-backups.md)
