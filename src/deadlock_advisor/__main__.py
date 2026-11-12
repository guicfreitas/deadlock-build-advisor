"""Entry point:  python -m deadlock_advisor [--no-overlay] [--no-panel] [--match-id N]
                                         [--hero NAME --enemies A,B,... --lane A,B]

Also the entry point of the installed .exe (PyInstaller, no console): output goes to
%LOCALAPPDATA%\\deadlock-advisor\\advisor.log and a second launch just opens the page.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)   # running as the PyInstaller .exe
LOG_MAX_BYTES = 2_000_000


def log_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "deadlock-advisor"


def _redirect_output() -> None:
    """A windowed .exe has no console: sys.stdout is None and print() would crash."""
    d = log_dir()
    d.mkdir(parents=True, exist_ok=True)
    log = d / "advisor.log"
    if log.exists() and log.stat().st_size > LOG_MAX_BYTES:
        log.replace(log.with_suffix(".old.log"))
    f = open(log, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - lives as long as the app
    f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    sys.stdout = sys.stderr = f


def _resolve(advisor, names: str) -> list[int]:
    cat = advisor.catalog
    lookup = {}
    for hid, h in cat.heroes.items():
        for key in (h["name"], h.get("class_name", "").removeprefix("hero_"), str(hid)):
            lookup[key.lower().replace(" ", "")] = hid
    out = []
    for n in filter(None, (x.strip() for x in names.split(","))):
        key = n.lower().replace(" ", "")
        if key not in lookup:
            sys.exit(f"Herói desconhecido: {n}")
        out.append(lookup[key])
    return out


def _relaunch_command() -> list[str]:
    if FROZEN:
        return [sys.executable, "--restarted", "--no-browser"]
    return [sys.executable, "-m", "deadlock_advisor", "--restarted", "--no-browser"]


def main(argv=None) -> None:
    if FROZEN and sys.stdout is None:
        _redirect_output()

    from .app import Advisor
    from .config import load_config
    from .server import PortInUse, serve

    ap = argparse.ArgumentParser(prog="deadlock_advisor", description="Deadlock Build Advisor")
    ap.add_argument("--no-overlay", action="store_true", help="só a página web, sem overlay")
    ap.add_argument("--no-panel", action="store_true", help="sem janela de controle (terminal)")
    ap.add_argument("--no-browser", action="store_true", help="não abrir o navegador ao iniciar")
    ap.add_argument("--restarted", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--match-id", type=int, help="forçar uma partida (ex.: testar com partida ativa)")
    ap.add_argument("--hero", help="modo offline: seu herói (nome)")
    ap.add_argument("--enemies", default="", help="modo offline: heróis inimigos, separados por vírgula")
    ap.add_argument("--lane", default="", help="modo offline: inimigos da sua lane")
    args = ap.parse_args(argv)

    cfg = load_config()
    advisor = Advisor(cfg)

    if args.hero:  # one-shot CLI mode, prints JSON
        hero = _resolve(advisor, args.hero)[0]
        rec = advisor.compute(hero, _resolve(advisor, args.enemies), _resolve(advisor, args.lane))
        print(json.dumps(rec, indent=2, ensure_ascii=False))
        return

    url = f"http://localhost:{cfg.port}"
    try:
        httpd = serve(advisor, cfg.port, wait_s=15 if args.restarted else 0)
    except PortInUse:
        # already running (double-clicked the shortcut again): show it instead of failing
        print(f"Já está rodando em {url}; abrindo a página.")
        webbrowser.open(url)
        return

    def quit_app() -> None:
        httpd.shutdown()
        os._exit(0)  # daemon threads (log watcher, streams) must not keep the process alive

    def restart() -> None:
        subprocess.Popen(_relaunch_command(), env=os.environ.copy(), close_fds=True)
        quit_app()

    advisor.on_restart = restart
    print(f"Deadlock Build Advisor rodando em {url}")
    print(f"Conta: {cfg.account_id or 'NÃO DETECTADA'} · log: {cfg.console_log} · config: {cfg.path}")
    advisor.start_watcher()
    if args.match_id:
        advisor.start_match(args.match_id)
    if not args.no_browser:
        webbrowser.open(url)

    show_overlay = cfg.overlay and not args.no_overlay
    if not args.no_panel:
        from .panel import Panel
        Panel(advisor, url, show_overlay, cfg.overlay_alpha, on_quit=quit_app).run()
        return
    if show_overlay:
        from .overlay import Overlay
        Overlay(advisor, cfg.overlay_alpha).run()
        return
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
