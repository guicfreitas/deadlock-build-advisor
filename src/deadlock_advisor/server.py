"""Local web UI. Open http://localhost:8787 in a second monitor, phone, or the
Steam overlay browser (Shift+Tab -> web browser) to see it in-game."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import urlparse

from .app import Advisor

STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "application/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}


def make_handler(advisor: Advisor):
    web = resources.files("deadlock_advisor") / "web"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj).encode(), "application/json; charset=utf-8")

        def do_GET(self):
            path = urlparse(self.path).path
            if path in STATIC:
                name, ctype = STATIC[path]
                return self._send(200, (web / name).read_bytes(), ctype)
            if path == "/api/state":
                return self._json(advisor.state.snapshot())
            if path == "/api/setup":  # re-run on demand, e.g. after the user fixes Steam
                check = advisor.setup_check()
                advisor.state.update(setup=check)
                return self._json(check)
            if path == "/api/heroes":
                try:
                    cat = advisor.catalog
                except Exception as e:  # noqa: BLE001
                    return self._json({"error": str(e)}, 502)
                return self._json(sorted((cat.hero_view(h) for h in cat.heroes), key=lambda h: h["name"]))
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._json({"error": "json inválido"}, 400)
            if path == "/api/manual":
                try:
                    hero = int(body["hero_id"])
                    enemies = [int(x) for x in body.get("enemies", [])]
                    lane = [int(x) for x in body.get("lane_enemies", [])]
                except (KeyError, ValueError, TypeError):
                    return self._json({"error": "hero_id/enemies inválidos"}, 400)
                threading.Thread(target=lambda: _safe(advisor.compute_manual, hero, enemies, lane),
                                 daemon=True).start()
                return self._json({"ok": True})
            if path == "/api/match":
                try:
                    advisor.start_match(int(body["match_id"]))
                except (KeyError, ValueError, TypeError):
                    return self._json({"error": "match_id inválido"}, 400)
                return self._json({"ok": True})
            self._send(404, b"not found", "text/plain")

    return Handler


def _safe(fn, *a):
    try:
        fn(*a)
    except Exception:  # noqa: BLE001 - already reported in state
        pass


def serve(advisor: Advisor, port: int) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(advisor))
    threading.Thread(target=httpd.serve_forever, daemon=True, name="web").start()
    return httpd
