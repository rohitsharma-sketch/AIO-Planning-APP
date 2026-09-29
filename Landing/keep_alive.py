"""Keeps Landing (7800) running - the one server nothing else watches (2026-09-29: Landing went down with a
session restart and took every link with it). Landing itself relaunches every other app within 30 s
(landing_server._watchdog), so bringing Landing back brings the whole suite back.

Run by the scheduled task "RS Planning - Keep Alive" (install_keep_alive.ps1): at sign-in and every 2 minutes,
under pythonw (no window). Does nothing when 7800 is already up.
"""
import os
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 7800


def is_up(port=PORT):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def main():
    if is_up():
        return
    # python.exe, not pythonw: Landing's apps inherit it (uvicorn needs real stdout/stderr); DETACHED = no console
    py = os.path.join(os.path.dirname(sys.executable), "python.exe")
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    with open(os.path.join(HERE, "keep_alive.log"), "a") as log:
        subprocess.Popen([py, "landing_server.py", "--no-browser"], cwd=HERE, creationflags=flags,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log)


if __name__ == "__main__":
    main()
