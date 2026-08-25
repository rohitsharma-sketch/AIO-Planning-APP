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

import psutil

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


def _pid_listening_on(port):
    # LISTEN-only, loopback/any-addr - matches _is_online's own definition of
    # "online" so launch/shutdown agree on what counts as this app's process.
    for conn in psutil.net_connections(kind="inet"):
        if conn.status == psutil.CONN_LISTEN and conn.laddr and conn.laddr.port == port and conn.pid:
            return conn.pid
    return None


def _shutdown_many(ports_and_names):
    # terminate() every listening app FIRST - each call is near-instant, it
    # only sends the signal - then wait for all of them together. Doing
    # terminate-then-wait one app at a time meant a slow-to-exit app blocked
    # the NEXT app's terminate() from even being sent, so worst case stacked
    # up to len(apps) x one grace period sequentially. Waiting concurrently
    # instead bounds total wall time by the single slowest app, not their sum.
    procs, missing = {}, []
    for port, name in ports_and_names:
        pid = _pid_listening_on(port)
        if pid is None:
            missing.append(name)
            continue
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            procs[proc] = name
        except psutil.NoSuchProcess:
            missing.append(name)

    gone, alive = psutil.wait_procs(list(procs.keys()), timeout=3)
    for proc in alive:
        proc.kill()

    return [procs[p] for p in procs], missing


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
        if self.path == "/api/launch-all":
            self._launch_all()
        elif self.path == "/api/shutdown-all":
            self._shutdown_all()
        else:
            self.send_response(404)
            self.end_headers()

    def _json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _launch_all(self):
        launched, already_online = [], []
        for app in APPS:
            if _is_online(app["port"]):
                already_online.append(app["name"])
            else:
                _launch(app)
                launched.append(app["name"])
        self._json({"ok": True, "launched": launched, "alreadyOnline": already_online})

    def _shutdown_all(self):
        stopped, already_offline = _shutdown_many([(app["port"], app["name"]) for app in APPS])
        self._json({"ok": True, "stopped": stopped, "alreadyOffline": already_offline})


if __name__ == "__main__":
    os.chdir(_HERE)
    webbrowser.open(f"http://localhost:{PORT}")
    print(f"RS Planning landing page at http://localhost:{PORT}")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
