# 1. Install & launch

## What you need

- A Mac
- Internet (first install only)
- Xcode Command Line Tools / Homebrew optional but useful for HTTPS certs later

## Steps

1. Clone the repo:
   ```bash
   git clone https://github.com/Adi1yer/Personal-Finance-App.git
   cd Personal-Finance-App
   ```
2. Install dependencies:
   ```bash
   make setup
   ```
   Expect several minutes the first time (Python venv + frontend packages).
3. Launch (pick one):
   ```bash
   make launch
   ```
   Or build a double-clickable Mac app (needs Xcode Command Line Tools / `clang`):
   ```bash
   make mac-app
   ```
   Then open **Finder → Applications (in your home folder) → Personal Finance**.  
   Do **not** dig into Package Contents / Terminal for normal use.

## What you should see

- A dark desktop window titled **Personal Finance** (no Terminal window)
- Either a **login** screen or the main sidebar (Overview, Accounts, …) after you sign in
- On sign-up: a recovery code with a **Copy recovery code** button

## If something goes wrong

| What you see | What to do |
|--------------|------------|
| `make` / Python errors | Ensure you’re in the repo root; run `make setup` again |
| Icon click does nothing | Re-run `make mac-app` from the clone; then `xattr -cr ~/Applications/Personal\ Finance.app` and double-click again. Check `~/Library/Application\ Support/PersonalFinance/logs/` |
| Terminal opens when starting the app | You’re on an old app build — re-run `make mac-app` (uses a native launcher) |
| `clang not found` during `make mac-app` | Run `xcode-select --install`, then `make mac-app` again |
| Window opens then blank | Wait for first-time setup; check logs under Application Support |
| Port 8000 in use | Quit other copies (`make stop`) and relaunch |
| Moved the git clone after `make mac-app` | Run `make mac-app` again so the app points at the new path |

Next: [Create your login](02-create-login.md)
