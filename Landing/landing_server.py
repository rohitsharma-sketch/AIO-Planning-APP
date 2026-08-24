"""
RS Planning landing page — static file server, port 7800.
Run: python landing_server.py
"""
import json
import os
import socket
import subprocess
import sys
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

PORT = 7800
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)

# One-click "bring online": the exact commands/working directories this
# session already uses to start each app by hand. Landing itself (7800) is
# never included here — if this endpoint is being hit at all, it's already
# running. Each entry launches detached (its own process group) so it
# outlives landing_server.py, exactly like starting it from its own terminal.
APPS = [
    {"name": "Buyer's Input", "port": 5050,
     "cmd": [sys.executable, "sync_server.py"],
     "cwd": os.path.join(_REPO_ROOT, "Buyer's Input Sheet")},
    {"name": "Calendar Engine (standalone)", "port": 7822,
     "cmd": [sys.executable, "local_server.py"],
     "cwd": os.path.join(_REPO_ROOT, "Calendar Engine")},
    {"name": "AOP Forecaster (standalone)", "port": 8000,
     "cmd": [sys.executable, "-m", "uvicorn", "app:app", "--port", "8000"],
     "cwd": os.path.join(_REPO_ROOT, "Tentative AOP Forecaster")},
    {"name": "Planning Engine (standalone)", "port": 8002,
     "cmd": [sys.executable, "-m", "uvicorn", "main:app", "--port", "8002"],
     "cwd": os.path.join(_REPO_ROOT, "SalesPlan", "backend")},
    {"name": "RS Planning Platform", "port": 8010,
     "cmd": [sys.executable, "-m", "uvicorn", "app:app", "--port", "8010"],
     "cwd": os.path.join(_REPO_ROOT, "RS Planning Platform", "backend")},
]


def _is_online(port, timeout=0.5):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _launch(app):
    # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP: fully independent of this
    # server's own process, matching how starting it from a separate terminal
    # behaves - it must keep running even if landing_server.py is later closed.
    creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    subprocess.Popen(
        app["cmd"], cwd=app["cwd"], creationflags=creationflags,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
    )


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        if self.path != "/api/launch-all":
            self.send_response(404)
            self.end_headers()
            return

        launched, already_online = [], []
        for app in APPS:
            if _is_online(app["port"]):
                already_online.append(app["name"])
            else:
                _launch(app)
                launched.append(app["name"])

        body = json.dumps({"ok": True, "launched": launched, "alreadyOnline": already_online}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    os.chdir(_HERE)
    webbrowser.open(f"http://localhost:{PORT}")
    print(f"RS Planning landing page at http://localhost:{PORT}")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
