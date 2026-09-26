"""Listing/Delisting app server (port 8123) - launched and watched by Landing.

Plain static serving of app/, but with `Cache-Control: no-cache`, because the daily
data-lake sync rewrites app/*.json in place: without it browsers kept showing the
previous day's files (python -m http.server lets them cache heuristically).
Run manually: python serve.py
"""
import functools
import http.server
import os

PORT = int(os.environ.get("LISTING_PORT", "8123"))
APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")   # revalidate every time (cheap 304 when unchanged)
        super().end_headers()


if __name__ == "__main__":
    handler = functools.partial(NoCacheHandler, directory=APP_DIR)
    # loopback only - reached via Landing /listing/ (one address)
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler).serve_forever()
