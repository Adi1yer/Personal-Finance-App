# Security

## What stays on your Mac

| Path | Contents |
|------|----------|
| `data/registry.db` | Logins (password hashes) |
| `data/profiles/<id>/ledger.db` | Your transactions and balances |
| `data/app_config.json` | BYO Plaid / Google / encryption keys (from Setup) |
| `.env` | Optional env overrides (same secrets) |
| `data/certs/` | Local HTTPS cert for OAuth banks |

Nothing above is meant for git or public sharing.

## What not to commit

- `.env`, `.env.local`
- `data/` (databases, `app_config.json`, certs)
- Real Plaid secrets, Google client secrets, `ENCRYPTION_KEY`
- Exported ledger ZIPs or Drive backup downloads

The public repo should only contain code and docs. Use `.gitignore` as shipped.

## Auth model

- Email + password → JWT stored in the desktop/web UI
- Optional recovery code for password reset (shown once at signup)
- Plaid and Google tokens are encrypted at rest with `ENCRYPTION_KEY`

## Localhost setup API

`/api/v1/setup/*` only accepts requests from `127.0.0.1` / `::1`. Do not expose the API to the public internet without additional hardening.

## Tips

- Prefer generating a unique encryption key per machine
- Use Plaid **Sandbox** until you are ready for production OAuth
- Google OAuth apps in Testing mode only allow listed test users — add your own email
- Quit the app with Cmd+Q so quit-time Drive backup can finish when connected
