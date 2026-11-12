"""Orchestrator: log events -> roster -> recommendation -> shared state for UI/overlay."""
from __future__ import annotations

import threading
import time
import traceback
from dataclasses import fields
from pathlib import Path

from .api import DeadlockApi
from .config import Config
from .engine import Catalog, EngineConfig, Recommender
from .live import Roster, fetch_roster, watch_roster
from .logwatch import ConsoleLogWatcher, LogEvent


def _lane_key(roster: Roster) -> tuple:
    """What the lane build depends on: my hero and the enemy heroes in my lane."""
    return roster.me.hero_id, tuple(sorted(p.hero_id for p in roster.lane_enemies))


class AppState:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {"status": "idle", "message": "Aguardando partida…", "match_id": None,
                      "roster": None, "recommendation": None, "updated_at": time.time()}
        self.version = 0

    def update(self, **kw):
        with self._lock:
            self._data.update(kw)
            self._data["updated_at"] = time.time()
            self.version += 1

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data) | {"version": self.version}


class Advisor:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.state = AppState()
        self.api = DeadlockApi(Path(cfg.cache_dir), cfg.api_key)
        ecfg = EngineConfig()
        for f in fields(EngineConfig):
            if f.name in cfg.engine:
                setattr(ecfg, f.name, cfg.engine[f.name])
        self.engine_cfg = ecfg
        self._catalog: Catalog | None = None
        self._job_lock = threading.Lock()
        self._current_job: int | None = None
        self.watcher: ConsoleLogWatcher | None = None
        self.lane_watch_s = 300  # how long to keep watching for lane swaps after the first build

    @property
    def catalog(self) -> Catalog:
        if self._catalog is None:
            self._catalog = Catalog(self.api.heroes(), self.api.upgrade_items())
        return self._catalog

    @property
    def recommender(self) -> Recommender:
        return Recommender(self.api, self.catalog, self.engine_cfg)

    # ------------------------------------------------------------ lifecycle
    def start_watcher(self) -> None:
        log = self.cfg.console_log
        if not log.exists():
            self.state.update(status="setup", message=(
                f"console.log não encontrado em {log}. Adicione -condebug nas opções de "
                "inicialização do Deadlock na Steam."))
        self.watcher = ConsoleLogWatcher(log, self.on_log_event)
        self.watcher.start()

    def on_log_event(self, ev: LogEvent) -> None:
        if ev.kind == "match_found" and ev.match_id:
            self.start_match(ev.match_id)
        elif ev.kind in ("match_ended", "game_closed"):
            with self._job_lock:
                self._current_job = None
            snap = self.state.snapshot()
            if snap["status"] != "idle":
                self.state.update(status="idle", message="Partida encerrada. Aguardando a próxima…")

    def start_match(self, match_id: int) -> None:
        with self._job_lock:
            if self._current_job == match_id:
                return
            self._current_job = match_id
        self.state.update(status="loading", match_id=match_id, roster=None, recommendation=None,
                          message=f"Partida {match_id} encontrada. Lendo heróis dos adversários…")
        threading.Thread(target=self._match_job, args=(match_id,), daemon=True).start()

    def _still_current(self, match_id: int) -> bool:
        return self._current_job == match_id

    def _match_job(self, match_id: int) -> None:
        try:
            account = self.cfg.detect_account_id()
            if not account:
                raise RuntimeError("account_id não detectado; defina em config.json")

            def status(msg: str):
                if self._still_current(match_id):
                    self.state.update(message=f"Partida {match_id}: {msg}")

            roster = fetch_roster(self.api, match_id, account, on_status=status)
            if not self._still_current(match_id):
                return
            if roster.game_mode == "street_brawl":
                self.state.update(status="idle", message=(
                    "Briga de rua: os itens vêm por draft, sem compra. Não há build para recomendar."))
                return
            self._apply_roster(roster, "Heróis identificados. Calculando builds…")
        except Exception as e:  # noqa: BLE001 - surface any failure in the UI
            traceback.print_exc()
            if self._still_current(match_id):
                self.state.update(status="error", message=f"Erro: {e}. Use o modo manual na página.")
            return
        # Lanes can still be swapped right after the match starts: keep watching for a few
        # minutes and redo the lane build if the enemy duo in my lane changes.
        threading.Thread(target=self._watch_lanes, args=(match_id, account, roster),
                         daemon=True, name="lane-watch").start()

    def _apply_roster(self, roster, message: str) -> None:
        cat = self.catalog
        self.state.update(roster={
            "me": roster.me.to_dict(),
            "game_mode": roster.game_mode,
            "players": [p.to_dict() | {"hero": cat.hero_name(p.hero_id)} for p in roster.players],
        }, message=message)
        self.compute(roster.me.hero_id, [p.hero_id for p in roster.enemies],
                     [p.hero_id for p in roster.lane_enemies], match_id=roster.match_id)

    def _watch_lanes(self, match_id: int, account: int, roster) -> None:
        current = {"key": _lane_key(roster)}

        def on_change(new_roster):
            key = _lane_key(new_roster)
            if key == current["key"] or not self._still_current(match_id):
                return
            current["key"] = key
            names = ", ".join(self.catalog.hero_name(h) for h in key[1]) or "desconhecida"
            try:
                self._apply_roster(new_roster, f"Lane mudou (agora contra {names}). Recalculando…")
                if self._still_current(match_id):
                    self.state.update(message=f"Lane atualizada: agora contra {names}. Build de lane recalculada.")
            except Exception:  # noqa: BLE001 - keep the previous build on screen
                traceback.print_exc()

        watch_roster(self.api, match_id, account, on_change,
                     duration_s=self.lane_watch_s, should_continue=lambda: self._still_current(match_id))

    def compute(self, hero_id: int, enemies: list[int], lane_enemies: list[int], match_id: int | None = None) -> dict:
        rec = self.recommender.recommend(hero_id, enemies, lane_enemies)
        if match_id is None or self._still_current(match_id):
            self.state.update(status="ready", recommendation=rec,
                              message=f"Build pronta para {rec['hero']['name']}.")
        return rec

    def compute_manual(self, hero_id: int, enemies: list[int], lane_enemies: list[int]) -> dict:
        with self._job_lock:
            self._current_job = None
        self.state.update(status="loading", match_id=None, message="Calculando build (modo manual)…")
        try:
            return self.compute(hero_id, enemies, lane_enemies)
        except Exception as e:  # noqa: BLE001
            self.state.update(status="error", message=f"Erro: {e}")
            raise
