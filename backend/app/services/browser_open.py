"""Open URLs in a system browser (OAuth / Plaid link flows)."""

from __future__ import annotations

import platform
import subprocess
import webbrowser


def open_in_browser(url: str) -> str:
    """Prefer Safari on macOS — Brave/Chrome block self-signed local certs more aggressively."""
    if platform.system() == "Darwin":
        subprocess.run(["open", "-a", "Safari", url], check=False)
        return "Safari"
    webbrowser.open(url)
    return "default"


def open_plaid_link(url: str) -> str:
    return open_in_browser(url)
