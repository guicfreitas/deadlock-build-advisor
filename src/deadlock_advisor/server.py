"""Local web UI. Open http://localhost:8787 in a second monitor, phone, or the
Steam overlay browser (Shift+Tab -> web browser) to see it in-game."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import urlparse

from . import clipboard, config, gamebuild
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
                if check["ok"] and advisor.state.snapshot()["status"] == "setup":
                    advisor.state.update(status="idle", message="Aguardando partida…")
                return self._json(check)
            if path == "/api/settings":
                return self._json(config.settings_view(advisor.cfg))
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
            if path == "/api/copy-build":  # share code for the game's "Colar guia" button
                rec = advisor.state.snapshot().get("recommendation")
                if not rec:
                    return self._json({"error": "nenhuma build calculada ainda"}, 409)
                if blocked := advisor.copy_blocked():
                    return self._json({"error": blocked}, 409)
                build = gamebuild.from_recommendation(rec, advisor.cfg.account_id)
                code = build.share_code()
                copied = clipboard.set_text(code)
                advisor.mark_copied(build)  # from now on, counters compare against this build
                return self._json({"ok": True, "copied": copied, "code": code})
            if path == "/api/settings":
                if not isinstance(body, dict):
                    return self._json({"error": "json inválido"}, 400)
                try:
                    result = config.update_settings(advisor.cfg, body)
                except OSError as e:
                    return self._json({"error": f"não consegui salvar: {e}"}, 500)
                if not result["errors"]:
                    advisor.reload_settings()
                return self._json(result | {"settings": config.settings_view(advisor.cfg)},
                                  400 if result["errors"] else 200)
            if path == "/api/update":
                if not advisor.updater:
                    return self._json({"error": "atualização automática indisponível"}, 409)
                r = advisor.updater.install()
                return self._json(r, 409 if r.get("error") else 200)
            if path == "/api/restart":
                if not advisor.on_restart:
                    return self._json({"error": "reinício automático indisponível; feche e abra o app"}, 409)
                self._json({"ok": True})
                threading.Timer(0.5, advisor.on_restart).start()
                return None
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


class PortInUse(OSError):
    pass


class _ExclusiveServer(ThreadingHTTPServer):
    """http.server turns on SO_REUSEADDR, and on Windows that lets a second process bind the
    same port: two copies of the app would run side by side. Own the port exclusively so a
    second launch fails to bind and opens the page of the first one instead."""
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        import socket
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def serve(advisor: Advisor, port: int, wait_s: float = 0) -> ThreadingHTTPServer:
    """Start the web UI. wait_s > 0 retries while the port is busy (a restart: the old
    process is still shutting down)."""
    import time
    deadline = time.time() + wait_s
    while True:
        try:
            httpd = _ExclusiveServer(("127.0.0.1", port), make_handler(advisor))
            break
        except OSError as e:
            if time.time() >= deadline:
                raise PortInUse(f"porta {port} em uso") from e
            time.sleep(0.3)
    threading.Thread(target=httpd.serve_forever, daemon=True, name="web").start()
    return httpd
