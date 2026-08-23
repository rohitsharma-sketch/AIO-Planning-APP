"""
RS Planning landing page — static file server, port 7800.
Run: python landing_server.py
"""
import os
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

PORT = 7800


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    webbrowser.open(f"http://localhost:{PORT}")
    print(f"RS Planning landing page at http://localhost:{PORT}")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
