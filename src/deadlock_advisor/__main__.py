"""Entry point:  python -m deadlock_advisor [--no-overlay] [--match-id N]
                                         [--hero NAME --enemies A,B,... --lane A,B]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser

from .app import Advisor
from .config import load_config
from .server import serve


def _resolve(advisor: Advisor, names: str) -> list[int]:
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


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="deadlock_advisor", description="Deadlock Build Advisor")
    ap.add_argument("--no-overlay", action="store_true", help="só a página web, sem overlay")
    ap.add_argument("--no-browser", action="store_true", help="não abrir o navegador ao iniciar")
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

    serve(advisor, cfg.port)
    url = f"http://localhost:{cfg.port}"
    print(f"Deadlock Build Advisor rodando em {url}")
    print(f"Conta: {cfg.account_id or 'NÃO DETECTADA'} · log: {cfg.console_log}")
    advisor.start_watcher()
    if args.match_id:
        advisor.start_match(args.match_id)
    if not args.no_browser:
        webbrowser.open(url)

    if cfg.overlay and not args.no_overlay:
        from .overlay import Overlay
        Overlay(advisor, cfg.overlay_alpha).run()
    else:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
