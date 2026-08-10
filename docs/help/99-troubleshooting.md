# Troubleshooting

## App won’t open from the icon

| Symptom | Fix |
|---------|-----|
| Click icon → nothing | Re-run `make mac-app`; clear quarantine: `xattr -cr ~/Applications/Personal\ Finance.app`; open again |
| Only works via Package Contents / Terminal | Old shell-script app — rebuild with current `make mac-app` (native `PersonalFinance` launcher) |
| Alert: project folder missing/moved | Clone path changed — `cd` into the repo and `make mac-app` again |
| Logs | `~/Library/Application Support/PersonalFinance/logs/launch.log` and `app-launch.log` |

## Sign-up / recovery code

| Symptom | Fix |
|---------|-----|
| Can’t copy recovery code | Use **Copy recovery code**; click the code field then Cmd+C. Rebuild UI (`make build-ui` or relaunch so dist updates) if the button is missing |
| Lost recovery code | Settings → Password → **New recovery code** while signed in |

## Connections / keys

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| “Plaid not configured” | Missing client_id/secret or encryption key | Settings → Connections setup → save keys; generate encryption key |
| “Google Drive not configured” | Missing OAuth client | Paste Web application client ID/secret; save |
| Secrets don’t persist | `data/` not writable | Check permissions on the project `data/` folder |

## Plaid / bank

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Redirect URI mismatch | Dashboard URI ≠ app URI | Copy URI from Connections setup into Plaid Allowed redirect URIs |
| OAuth bank fails (e.g. Chase) | Sandbox or HTTP only | Production env + `make trust-cert` + HTTPS redirect |
| Browser never opens | Popup / OS block | Use the manual URL shown in Settings |
| “This Connection Is Not Private” | Local HTTPS cert | Safari Show Details → visit website; or trust mkcert |
| Sync empty | Unmapped accounts | Map Plaid accounts → Sync now |
| Pending bank deposit missing | Bank/Plaid lag | Wait until posted; re-sync |

## Google Drive

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| 403 access_denied | Not a test user | Cloud Console → Audience → Test users → add your Gmail |
| App not verified | Testing mode | Continue via Advanced for your own client |
| Connection dropped on redirect | API down / wrong scheme | Keep app running; use `https://localhost:8000/...` if production TLS is on |
| Desktop OAuth client | No redirect URI UI | Create **Web application** client instead |
| Backup fails | Not connected / offline | Connect first; check Drive API enabled |

## Accounts / goals

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Investing goal low | Manual 401(k)/HSA not counted | Set **Total contributions** to YTD total |
| Brokerage deposits not counting | Naming/category | Ensure transfers/contributions sync; check Goals breakdown |
| Income looks wrong | Paycheck not categorized | Fix categories / sync income accounts |

## Advisor

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Offline | Ollama not running | Start Ollama; `ollama pull <model>` |
| Weird answers | Wrong model name | Match Preferences to `ollama list` |
| Setup questions vague | Didn’t open help | Ask “read the Google Drive help guide” or use setup chips |

## Still stuck

1. Ask Advisor: “Check my setup status and tell me the next step.”
2. Skim [Connections setup](03-connections-keys.md) and [Troubleshooting](#troubleshooting) again.
3. Confirm you’re on the latest `main` from the repo.
