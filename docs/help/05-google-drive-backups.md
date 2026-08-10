# 5. Google Drive backups

Prerequisites: Google OAuth **configured** in Connections setup ([guide](03-connections-keys.md)), including your email as a **test user**.

## Connect

1. **Settings → Google Drive backups**.
2. Click **Connect Google Drive**.
3. Browser opens Google sign-in — use the Gmail you added as a test user.
4. You may see **“Google hasn’t verified this app”** — for a Testing app this is normal. Continue (Advanced → Go to …) if you trust your own OAuth client.
5. Approve Drive access (files created by this app).
6. Google redirects to `https://localhost:8000/oauth/google-drive.html`.

### Local HTTPS warning

Same as bank Link: Safari may say the connection is not private. **Show Details → visit this website**. You should then see **“Google Drive connected!”** with your email.

7. Return to the app. Status should read **Connected as you@gmail.com**.

## Backup now

1. Click **Backup now**.
2. Message should mention an uploaded zip (e.g. `ledger-….zip`) and that the last 5 are kept.
3. In Google Drive, look for folder **Personal Finance Backups**.

## Restore

1. **Refresh list** under Cloud snapshots.
2. Click **Restore** on a snapshot (confirms first; keeps a local safety copy).

## Quit backup

When Drive is connected, quitting the Mac app (**Cmd+Q** or close the window) uploads a snapshot before exit. Prefer a normal quit over force-quit so the upload can finish.

## Common errors

| Symptom | Fix |
|---------|-----|
| 403 access_denied / not verified | Add yourself under OAuth **Test users**; wait a minute and retry |
| “access expired or was revoked” / Backup fails | Google refresh token died (common in Testing mode). **Connect Google Drive** again |
| Safari can’t open localhost / connection dropped | API not running, or HTTP vs HTTPS mismatch — use the redirect URI from Settings; ensure app is up |
| Desktop client has no redirect field | Create a **Web application** OAuth client instead |
| Configured but not connected | Click Connect and finish the browser flow |

Next: [Accounts & contributions](06-accounts-and-contributions.md)
