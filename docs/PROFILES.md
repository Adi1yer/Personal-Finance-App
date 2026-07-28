# Profiles & sign-in

Each **profile** is a separate ledger on your Mac, protected by email and password.

## Fresh start (no accounts)

When you **create a profile**, the app seeds only internal bookkeeping accounts (uncategorized expense, income buckets, etc.). Those are hidden from the Accounts list.

You add your own checking, cards, and investments under **Accounts → Add account**.

## Where data lives

| Data | Location |
|------|----------|
| Logins (email + password hash) | `data/registry.db` |
| Your ledger | `data/profiles/<profile-id>/ledger.db` |

Passwords are hashed with bcrypt. Sessions use a signed token stored in the app (localStorage).

## Old `data/finance.db`

If you used the app before profiles, that file is **not** used automatically. Create a new profile and add accounts again, or keep the old file as a backup.

## Sign out

**Settings → Sign out** clears the session. Sign in again to open the same profile’s data.

## Forgot password

This app is **local-only** — we cannot email you a reset link.

1. **Have your recovery code?** (shown once at signup, e.g. `amber-maple-stone-river`)  
   Sign-in screen → **Forgot password?** → email + recovery code + new password.

2. **No recovery code?** Reset from Terminal in the project folder:
   ```bash
   make reset-password EMAIL=you@example.com
   ```
   You’ll set a new password and get a **new recovery code** to save.

3. **Signed in?** **Settings → Password** — change password or generate a new recovery code.
