"""
RS Planning landing page — static file server + reverse proxy, port 7800.
Run: python landing_server.py

All sub-apps are exposed through this single port so the whole platform
is reachable at http://<host>:7800 from anywhere on the LAN.  Only port
7800 needs a firewall rule; the sub-app ports (5050, 8000, 8010) stay
loopback-only.

Proxy routing (first match wins):
  /buyer/*                       → http://127.0.0.1:5050  (BIS, prefix stripped)
  /api/otb/*, /api/status,
    /api/config/aop-div-targets  → http://127.0.0.1:5050  (BIS API, same path)
  /api/config/db-sync*           → http://127.0.0.1:8000  (AOP standalone, no auth)
  /calendar/, /aop/, /planning/,
    /plan-cycles, /auth/, /api/,
    /docs, /openapi.json         → http://127.0.0.1:8010  (unified platform)
  /api/launch-all, /api/shutdown-all, /api/port-status/* → handled here
  everything else                → serve Landing page files from this directory
"""
import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

import psutil

PORT = 7800
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)

# One-click "bring online": the exact commands/working directories this
# session already uses to start each app by hand.  Landing itself (7800)
# is never included here — if this endpoint is being hit at all, it's
# already running.  Each entry launches detached so it outlives landing_server.py.
#
# Calendar Engine and Planning Engine do NOT get their own standalone entries
# here (they did once, on ports 7822/8002) - both are served by the unified
# RS Planning Platform on 8010, so a standalone launch is pure duplication.
APPS = [
    {"name": "Buyer's Input", "port": 5050,
     "cmd": [sys.executable, "sync_server.py"],
     "cwd": os.path.join(_REPO_ROOT, "Buyer's Input Sheet")},
    # Deliberately kept standalone (unlike Calendar/Planning above) - the
    # unified :8010 route needs a login session, and this landing page's own
    # anonymous status checks and "sync data lake" trigger both need an
    # unauthenticated port.
    {"name": "AOP Forecaster (standalone)", "port": 8000,
     "cmd": [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8000"],
     "cwd": os.path.join(_REPO_ROOT, "Tentative AOP Forecaster")},
    {"name": "RS Planning Platform", "port": 8010,
     "cmd": [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8010"],
     "cwd": os.path.join(_REPO_ROOT, "RS Planning Platform", "backend")},
]

# Proxy route table — (path_prefix, target_base, strip_prefix).
# strip_prefix is removed from the request path before forwarding.
# An empty strip means the path is forwarded unchanged.
PROXY_ROUTES = [
    # BIS HTML — /buyer/* maps to / at 5050 (strip the /buyer prefix)
    ('/buyer',                           'http://127.0.0.1:5050', '/buyer'),
    # BIS API routes — same path at 5050
    ('/api/otb/',                        'http://127.0.0.1:5050', ''),
    ('/api/status',                      'http://127.0.0.1:5050', ''),
    # AOP standalone — sync endpoints and division targets (no auth required)
    ('/api/config/aop-division-targets', 'http://127.0.0.1:8000', ''),
    ('/api/config/db-sync',              'http://127.0.0.1:8000', ''),
    # Unified RS Planning Platform
    ('/calendar/',                       'http://127.0.0.1:8010', ''),
    ('/aop/',                            'http://127.0.0.1:8010', ''),
    ('/planning/',                       'http://127.0.0.1:8010', ''),
    ('/plan-cycles',                     'http://127.0.0.1:8010', ''),
    ('/auth/',                           'http://127.0.0.1:8010', ''),
    ('/login',                           'http://127.0.0.1:8010', ''),
    ('/change-password',                 'http://127.0.0.1:8010', ''),
    ('/reset-password',                  'http://127.0.0.1:8010', ''),
    ('/static/',                         'http://127.0.0.1:8010', ''),
    ('/api/',                            'http://127.0.0.1:8010', ''),
    ('/docs',                            'http://127.0.0.1:8010', ''),
    ('/openapi.json',                    'http://127.0.0.1:8010', ''),
]

_SKIP_REQ_HEADERS  = {'host', 'content-length'}
_SKIP_RESP_HEADERS = {'transfer-encoding', 'connection', 'content-length'}


def _find_proxy(path):
    """Return (target_base, rewritten_path) or (None, None). path must have no query string."""
    for prefix, target, strip in PROXY_ROUTES:
        if path == prefix or path.startswith(prefix if prefix.endswith('/') else prefix + '/'):
            new_path = path[len(strip):] if strip else path
            if not new_path or not new_path.startswith('/'):
                new_path = '/' + (new_path or '')
            return target, new_path
    return None, None


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
    # terminate() every listening app FIRST then wait for all of them together.
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
    creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    subprocess.Popen(
        app["cmd"], cwd=app["cwd"], creationflags=creationflags,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
    )


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        # Force a fresh load for the Landing page itself — sub-app responses
        # bypass this via _send_proxy_response → SimpleHTTPRequestHandler.end_headers.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        SimpleHTTPRequestHandler.end_headers(self)

    # ── proxy helpers ──────────────────────────────────────────────────────────

    def _proxy_target(self):
        """Compute full proxy URL from self.path, or None if no route matches."""
        full = self.path
        path = full.split('?')[0]
        target, new_path = _find_proxy(path)
        if target is None:
            return None
        q = full[full.index('?'):] if '?' in full else ''
        return target + new_path + q

    def _proxy(self, target_url):
        body = None
        cl = self.headers.get('Content-Length')
        if cl:
            body = self.rfile.read(int(cl))

        req = urllib.request.Request(target_url, data=body, method=self.command)
        for k, v in self.headers.items():
            if k.lower() not in _SKIP_REQ_HEADERS:
                req.add_header(k, v)

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                self._send_proxy_response(resp.status, resp.headers, resp.read())
        except urllib.error.HTTPError as e:
            self._send_proxy_response(e.code, e.headers, e.read())
        except Exception as e:
            self.send_error(502, f'Proxy error: {e}')

    # Internal backend origins that must never appear in a response sent to the
    # browser — any absolute URL pointing at these would break a remote client
    # (another machine) because its browser would follow the redirect to its own
    # localhost, where nothing is listening.
    _BACKEND_ORIGINS = [
        'http://127.0.0.1:8010', 'http://localhost:8010',
        'http://127.0.0.1:5050', 'http://localhost:5050',
        'http://127.0.0.1:8000', 'http://localhost:8000',
    ]

    def _rewrite_location(self, value):
        """Replace an internal backend origin with the public Landing origin."""
        public = 'http://' + self.headers.get('Host', f'localhost:{PORT}')
        for origin in self._BACKEND_ORIGINS:
            if value.startswith(origin):
                return public + value[len(origin):]
        return value

    def _send_proxy_response(self, status, headers, body):
        self.send_response(status)
        for k, v in headers.items():
            if k.lower() not in _SKIP_RESP_HEADERS:
                if k.lower() == 'location':
                    v = self._rewrite_location(v)
                self.send_header(k, v)
        self.send_header('Content-Length', str(len(body)))
        # Bypass the no-cache injection — sub-apps control their own caching.
        SimpleHTTPRequestHandler.end_headers(self)
        self.wfile.write(body)

    def _proxy_or_404(self):
        url = self._proxy_target()
        if url:
            self._proxy(url)
        else:
            self.send_response(404)
            self.end_headers()

    # BIS routes that require an active 8010 session before proxying through.
    _BIS_AUTH_PREFIXES = ('/buyer', '/api/otb/', '/api/status')

    def _is_bis_route(self):
        path = self.path.split('?')[0]
        return any(
            path == p or path.startswith(p if p.endswith('/') else p + '/')
            for p in self._BIS_AUTH_PREFIXES
        )

    def _is_authenticated(self):
        """Forward the incoming cookies to 8010's /api/auth/me; return True if 200."""
        try:
            req = urllib.request.Request('http://127.0.0.1:8010/api/auth/me')
            cookie = self.headers.get('Cookie', '')
            if cookie:
                req.add_header('Cookie', cookie)
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    # ── verb handlers ──────────────────────────────────────────────────────────

    def do_GET(self):
        # Local port-status endpoint: /api/port-status/<port>
        # Returns HTTP 200 (online) or 503 (offline) so the JS can distinguish
        # without mode:'no-cors' opacity.
        if self.path.startswith('/api/port-status/'):
            try:
                port = int(self.path.rsplit('/', 1)[-1].split('?')[0])
            except (ValueError, IndexError):
                self.send_error(400)
                return
            online = _is_online(port)
            body = json.dumps({"online": online}).encode()
            self.send_response(200 if online else 503)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            SimpleHTTPRequestHandler.end_headers(self)
            self.wfile.write(body)
            return

        # Auth gate for BIS — redirect to login if no valid 8010 session.
        if self._is_bis_route() and not self._is_authenticated():
            dest = '/login?next=' + self.path
            self.send_response(302)
            self.send_header('Location', dest)
            self.end_headers()
            return

        url = self._proxy_target()
        if url:
            self._proxy(url)
        else:
            super().do_GET()

    def _auth_guard_api(self):
        """For mutating BIS API routes: return 401 JSON if not authenticated."""
        if self._is_bis_route() and not self._is_authenticated():
            body = json.dumps({"detail": "Not authenticated"}).encode()
            self.send_response(401)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            SimpleHTTPRequestHandler.end_headers(self)
            self.wfile.write(body)
            return True
        return False

    def do_POST(self):
        if self.path == "/api/launch-all":
            self._launch_all()
        elif self.path == "/api/shutdown-all":
            self._shutdown_all()
        elif self._auth_guard_api():
            return
        else:
            self._proxy_or_404()

    def do_PUT(self):
        if not self._auth_guard_api():
            self._proxy_or_404()

    def do_PATCH(self):
        if not self._auth_guard_api():
            self._proxy_or_404()

    def do_DELETE(self):
        if not self._auth_guard_api():
            self._proxy_or_404()

    def do_OPTIONS(self): self._proxy_or_404()

    # ── Landing-only API ───────────────────────────────────────────────────────

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
