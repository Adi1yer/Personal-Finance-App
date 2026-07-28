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
3. Launch:
   ```bash
   make launch
   ```
   Or build a one-click app:
   ```bash
   make mac-app
   ```
   Then open **Applications → Personal Finance**.

## What you should see

- A dark desktop window titled **Personal Finance**
- Either a **login** screen or the main sidebar (Overview, Accounts, …) after you sign in
- No Terminal needed for daily use after the Mac app is installed

## If something goes wrong

| What you see | What to do |
|--------------|------------|
| `make` / Python errors | Ensure you’re in the repo root; run `make setup` again |
| Window opens then blank | Wait for the UI build; check `~/Library/Application Support/PersonalFinance/logs/` |
| Port 8000 in use | Quit other copies of the app (`make stop`) and relaunch |

Next: [Create your login](02-create-login.md)
