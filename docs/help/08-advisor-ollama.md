# 8. Local Advisor (Ollama)

The in-app **Advisor** is optional. It runs on your Mac via [Ollama](https://ollama.com) — no cloud LLM required.

## Install Ollama

1. Download and install from [ollama.com](https://ollama.com).
2. Open Terminal and pull a model:
   ```bash
   ollama pull llama3.1
   ```
   (Any chat-capable model works; larger models are slower but often better.)
3. Confirm the server:
   ```bash
   curl http://localhost:11434/api/tags
   ```

## Point the app at Ollama

1. **Settings → Preferences** (or Advisor settings)
2. Base URL: `http://localhost:11434`
3. Model name: exactly what you pulled (e.g. `llama3.1`)
4. Save

## Use the Advisor

1. Open **Advisor** in the sidebar.
2. Status should show online / ready (not “offline”).
3. Try setup prompts:
   - “How do I connect my bank with Plaid?”
   - “How do I back up to Google Drive?”
   - “Walk me through Connections setup”
4. For money questions, the Advisor uses **tools** against your ledger (balances, goals, setup status). It should not invent account numbers.

## Help docs

The Advisor can **read these help guides** when you ask setup questions. Prefer asking:

- “What should I expect when connecting Google Drive?”
- “How do I enter 401k contributions?”
- “What’s next if Plaid is configured but not connected?”

## If Advisor is offline

| Check | Action |
|-------|--------|
| Ollama app running | Open Ollama from Applications / menu bar |
| Model pulled | `ollama list` |
| URL / model mismatch | Fix Preferences |
| Firewall | Allow localhost:11434 |

Finance features (accounts, Plaid, Drive, Goals) work without the Advisor.
