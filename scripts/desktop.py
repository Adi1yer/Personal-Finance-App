#!/usr/bin/env python3
"""Native desktop window — started by Personal Finance.app (no Terminal)."""
from __future__ import annotations

import atexit
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
SUPPORT = Path.home() / "Library/Application Support/PersonalFinance"
DESKTOP_PID_FILE = SUPPORT / "desktop.pid"
LOG_DIR = SUPPORT / "logs"
WRAPPER_HTML = SUPPORT / "ui-wrapper.html"

sys.path.insert(0, str(BACKEND))

DIST = REPO_ROOT / "frontend" / "dist"
HOST = "127.0.0.1"
PORT = 8000
CERT_DIR = REPO_ROOT / "data" / "certs"
CERT_FILE = CERT_DIR / "localhost.pem"
KEY_FILE = CERT_DIR / "localhost-key.pem"
REMOTE_API = os.environ.get("PERSONAL_FINANCE_API_URL", "").strip().rstrip("/")


def _ensure_dev_cert() -> bool:
    """Return True if a trusted (mkcert) or existing cert is available."""
    script = REPO_ROOT / "scripts" / "ensure-dev-cert.sh"
    if script.is_file():
        subprocess.run(["bash", str(script)], check=False, cwd=str(REPO_ROOT))
    return CERT_FILE.is_file() and KEY_FILE.is_file()


def _use_local_https() -> bool:
    if REMOTE_API:
        return False
    sys.path.insert(0, str(BACKEND))
    from app.config import get_settings

    settings = get_settings()
    if settings.plaid_env != "production":
        return False
    _ensure_dev_cert()
    return CERT_FILE.is_file() and KEY_FILE.is_file()


def _app_url() -> str:
    scheme = "https" if _use_local_https() else "http"
    return f"{scheme}://{HOST}:{PORT}/"


def _log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "desktop.log").open("a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def _write_pid() -> None:
    SUPPORT.mkdir(parents=True, exist_ok=True)
    DESKTOP_PID_FILE.write_text(str(os.getpid()))


def _remove_pid() -> None:
    DESKTOP_PID_FILE.unlink(missing_ok=True)


def _free_port(port: int) -> None:
    try:
        out = subprocess.check_output(
            ["lsof", "-tiTCP:%s" % port, "-sTCP:LISTEN"],
            text=True,
        )
    except subprocess.CalledProcessError:
        return
    for pid in out.strip().split():
        if pid and int(pid) != os.getpid():
            try:
                os.kill(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
    time.sleep(0.3)


def _wait_for_health(url: str, timeout: float = 45.0) -> bool:
    import ssl

    deadline = time.time() + timeout
    ctx = ssl._create_unverified_context() if url.startswith("https://") else None
    while time.time() < deadline:
        try:
            with urlopen(f"{url.rstrip('/')}/health", timeout=1, context=ctx) as resp:
                if resp.status == 200:
                    return True
        except OSError:
            time.sleep(0.25)
    return False


def _ui_is_ready(url: str) -> bool:
    import ssl

    ctx = ssl._create_unverified_context() if url.startswith("https://") else None
    try:
        with urlopen(url, timeout=2, context=ctx) as resp:
            if "text/html" not in resp.headers.get("Content-Type", "").lower():
                return False
            body = resp.read(256).decode("utf-8", errors="ignore")
            return "<!DOCTYPE html>" in body or '<div id="root">' in body
    except OSError:
        return False


def _run_uvicorn() -> None:
    import uvicorn

    kwargs: dict = {
        "host": HOST,
        "port": PORT,
        "app_dir": str(BACKEND),
        "loop": "asyncio",
        "log_level": "warning",
    }
    if _use_local_https():
        kwargs["ssl_certfile"] = str(CERT_FILE)
        kwargs["ssl_keyfile"] = str(KEY_FILE)
        _log(f"Local HTTPS enabled ({CERT_FILE.name}) for Plaid OAuth")
    uvicorn.run("app.main:app", **kwargs)


def _build_wrapper_html() -> Path:
    index = DIST / "index.html"
    content = index.read_text(encoding="utf-8")
    injection = (
        "<script>window.personalFinance="
        + json.dumps({"apiBase": REMOTE_API})
        + ";</script>"
    )
    if "</head>" in content:
        content = content.replace("</head>", injection + "</head>", 1)
    else:
        content = injection + content
    SUPPORT.mkdir(parents=True, exist_ok=True)
    WRAPPER_HTML.write_text(content, encoding="utf-8")
    return WRAPPER_HTML


class _RemoteUIHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/ui-wrapper.html", "/"):
            content = WRAPPER_HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        return SimpleHTTPRequestHandler.do_GET(self)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def log_message(self, format: str, *args) -> None:
        return


def _run_static_ui_server() -> None:
    server = ThreadingHTTPServer((HOST, PORT), _RemoteUIHandler)
    server.serve_forever()


def _shutdown() -> None:
    _log("Shutting down")
    _remove_pid()
    _free_port(PORT)


def main() -> None:
    if not DIST.joinpath("index.html").is_file():
        _log("ERROR: frontend/dist missing")
        sys.exit(1)

    _write_pid()
    atexit.register(_shutdown)

    app_url = _app_url()

    if REMOTE_API:
        _log(f"Remote API mode: {REMOTE_API}")
        _free_port(PORT)
        _build_wrapper_html()
        app_url = f"http://{HOST}:{PORT}/"
        ui = threading.Thread(target=_run_static_ui_server, daemon=True)
        ui.start()
        if not _wait_for_health(REMOTE_API, timeout=15.0):
            _log("ERROR: remote API health check failed")
            sys.exit(1)
        if not _ui_is_ready(app_url):
            _log("ERROR: local UI failed to start")
            sys.exit(1)
    else:
        if not (_wait_for_health(app_url, timeout=1.5) and _ui_is_ready(app_url)):
            _free_port(PORT)
            _log("Starting local API")
            server = threading.Thread(target=_run_uvicorn, daemon=True)
            server.start()
            if not (_wait_for_health(app_url) and _ui_is_ready(app_url)):
                _log("ERROR: API/UI failed to start")
                sys.exit(1)

    _log(f"Opening window ({app_url})")
    import webview

    if _use_local_https():
        webview.settings["IGNORE_SSL_ERRORS"] = True

    webview.create_window(
        "Personal Finance",
        app_url,
        width=1320,
        height=880,
        min_size=(960, 640),
        text_select=True,
        background_color="#0B1220",
    )
    webview.start()
    _shutdown()


if __name__ == "__main__":
    main()
