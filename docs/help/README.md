# Help: set up every feature

This guide walks you through the same setup path as a full-featured install: local app → keys → bank → Drive backups → accounts/goals → local Advisor.

Follow the guides **in order** the first time. Later, jump to whichever topic you need.

| Step | Guide | What you get |
|------|--------|----------------|
| 1 | [Install & launch](01-install-and-launch.md) | App running on your Mac |
| 2 | [Create your login](02-create-login.md) | Profile + recovery code |
| 3 | [Connections setup (keys)](03-connections-keys.md) | Encryption, Plaid, Google OAuth |
| 4 | [Connect your bank (Plaid)](04-plaid-bank-connect.md) | Synced checking/cards/investments |
| 5 | [Google Drive backups](05-google-drive-backups.md) | Cloud ledger snapshots |
| 6 | [Accounts & contributions](06-accounts-and-contributions.md) | Chart of accounts, 401(k)/HSA YTD |
| 7 | [Annual goals](07-goals.md) | Investing % and safety net |
| 8 | [Local Advisor (Ollama)](08-advisor-ollama.md) | In-app AI help |

**Also see:** [Troubleshooting](99-troubleshooting.md) · [../SETUP.md](../SETUP.md) (short version) · [../SECURITY.md](../SECURITY.md)

## What “done” looks like

When everything is set up you should be able to:

- Open the Mac app and sign in
- See bank balances after **Sync**
- See Google Drive status as **Connected** and run **Backup now**
- Enter **Total contributions** for manual retirement/HSA accounts
- See Goals progress with a per-account breakdown
- Ask Advisor things like “How do I connect my bank?” and get steps from these docs

## Tips

- Keep Plaid in **Sandbox** until Link works; then move to **production** for a real bank.
- Google OAuth apps in **Testing** only allow emails listed as **test users**.
- Never share your `.env`, `data/`, or API secrets with anyone.
