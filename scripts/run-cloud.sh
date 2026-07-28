#!/usr/bin/env python3
"""Run the always-on cloud API with scheduled Plaid sync."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    os.chdir(REPO_ROOT)
    if not (REPO_ROOT / "frontend" / "dist" / "index.html").is_file():
        print("Building UI first…", file=sys.stderr)
        subprocess.check_call([str(REPO_ROOT / "scripts" / "build-ui.sh")])

    env = os.environ.copy()
    env.setdefault("API_HOST", "0.0.0.0")
    env.setdefault("CLOUD_SCHEDULER_ENABLED", "true")

    cmd = [
        str(REPO_ROOT / ".venv" / "bin" / "uvicorn"),
        "app.main:app",
        "--host",
        env.get("API_HOST", "0.0.0.0"),
        "--port",
        env.get("API_PORT", "8000"),
        "--app-dir",
        "backend",
    ]
    os.execvpe(cmd[0], cmd, env)


if __name__ == "__main__":
    main()
