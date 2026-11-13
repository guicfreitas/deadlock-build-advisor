"""Discover who is in the user's live match (heroes, teams, lanes).

Strategy:
1. /v1/matches/active?account_id=...  (cheap, but only covers the top ~200 matches)
2. /v1/matches/demo/live/query         (deadlock-api spectates the match and runs SQL
   over the live broadcast). Works for any match, rate-limited to ~6 spectates/hour
   without an API key -> one per match is plenty.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from typing import Callable

from .api import ApiError, DeadlockApi

STEAM64_BASE = 76561197960265728

ROSTER_SQL = (
    'SELECT tick, "m_steamID", "m_iTeamNum", "m_nAssignedLane", "m_bLaneSwapLocked", '
    '"m_PlayerDataGlobal__m_nHeroID" AS hero_id '
    "FROM CCitadelPlayerController "
    'WHERE "m_PlayerDataGlobal__m_nHeroID" > 0'
)


@dataclass
class Player:
    account_id: int
    hero_id: int
    team: int
    lane: int | None = None
    lane_locked: bool = False   # m_bLaneSwapLocked: lane swaps are over for this player

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Roster:
    match_id: int
    players: list[Player]
    me: Player
    game_mode: str = "normal"  # "normal" (6v6, 3 lanes) | "street_brawl" (4v4, one lane, lane=0)

    @property
    def lanes_locked(self) -> bool:
        """Every player's lane is final (the ~30 s swap window at the start is over)."""
        return bool(self.players) and all(p.lane_locked for p in self.players)

    @property
    def enemies(self) -> list[Player]:
        return [p for p in self.players if p.team != self.me.team]

    @property
    def allies(self) -> list[Player]:
        return [p for p in self.players if p.team == self.me.team and p.account_id != self.me.account_id]

    @property
    def lane_enemies(self) -> list[Player]:
        if self.me.lane is None:
            return []
        return [p for p in self.enemies if p.lane == self.me.lane]

    @property
    def lane_ally(self) -> list[Player]:
        if self.me.lane is None:
            return []
        return [p for p in self.allies if p.lane == self.me.lane]


def _build_roster(match_id: int, players: list[Player], account_id: int,
                  game_mode: str | None = None) -> Roster:
    me = next((p for p in players if p.account_id == account_id), None)
    if me is None:
        raise ApiError("Sua conta não foi encontrada nesta partida (confira account_id no config).")
    if game_mode is None:
        # Street Brawl is 4v4 and reports every lane as 0; normal is 6v6 with lanes 1/4/6.
        game_mode = "street_brawl" if len(players) <= 8 else "normal"
    return Roster(match_id, players, me, game_mode)


def roster_from_active(api: DeadlockApi, match_id: int, account_id: int) -> Roster | None:
    try:
        matches = api.active_matches(account_id)
    except ApiError:
        return None
    for m in matches:
        if int(m.get("match_id", 0)) != match_id:
            continue
        players = [
            Player(int(p["account_id"]), int(p["hero_id"]), int(p["team"]), None)
            for p in m.get("players", []) if p.get("hero_id")
        ]
        mode = "street_brawl" if m.get("game_mode") == 4 else "normal" if m.get("game_mode") == 1 else None
        try:
            return _build_roster(match_id, players, account_id, mode)
        except ApiError:
            return None
    return None


def roster_from_broadcast(api: DeadlockApi, match_id: int, account_id: int,
                          on_status: Callable[[str], None] = lambda s: None,
                          settle_s: float = 4.0, timeout_s: float = 120) -> Roster:
    latest: dict[int, Player] = {}
    complete_at: float | None = None
    last_new_at = time.time()
    started = time.time()
    for event, data in api.stream_sse("/v1/matches/demo/live/query",
                                      {"match_id": match_id, "query": ROSTER_SQL}, timeout=timeout_s):
        if event == "ping":
            pass
        elif event == "status":
            on_status(status_pt(data.get("message", "") if isinstance(data, dict) else str(data)))
        elif event == "error":
            msg = data.get("error") if isinstance(data, dict) else str(data)
            raise ApiError(msg or "erro no live query")
        elif event == "end":
            break
        else:
            p = _row_to_player(data)
            if p is None:
                continue
            if _merge(latest, p):
                last_new_at = time.time()
            if complete_at is None and len(latest) >= 12 and all(x.lane for x in latest.values()):
                complete_at = time.time()
                if all(x.lane_locked for x in latest.values()):
                    break  # lanes are final: no need to wait for swaps to settle
        if complete_at and time.time() - complete_at > settle_s:
            break  # keep reading a few seconds so lane swaps settle
        # Street Brawl (8 players, no lanes): done once nobody new shows up for a while.
        if complete_at is None and len(latest) >= 8 and time.time() - last_new_at > 3 * settle_s:
            break
        if time.time() - started > timeout_s:
            break
    if not latest:
        raise ApiError("Broadcast sem jogadores ainda.")
    return _build_roster(match_id, list(latest.values()), account_id)


def status_pt(msg: str) -> str:
    """deadlock-api reports its own retries in English; the page is in Portuguese."""
    low = msg.lower()
    if "not ready" in low:
        return "Aguardando a transmissão da Valve ficar pronta (costuma levar 1 a 2 min)…"
    if "spectat" in low:
        return "Conectando à transmissão ao vivo da partida…"
    return msg


def _row_to_player(data) -> Player | None:
    """One CCitadelPlayerController row -> Player (teams 2/3 mapped to the stats API's 0/1)."""
    if not isinstance(data, dict) or "m_steamID" not in data:
        return None
    sid = int(data["m_steamID"] or 0)
    if sid <= STEAM64_BASE or not data.get("hero_id"):
        return None
    team = int(data["m_iTeamNum"])
    lane = data.get("m_nAssignedLane")
    return Player(sid - STEAM64_BASE, int(data["hero_id"]), team - 2 if team >= 2 else team,
                  int(lane) if lane else None, bool(data.get("m_bLaneSwapLocked")))


def _merge(latest: dict[int, "Player"], p: "Player") -> bool:
    """Store a fresh row, keeping the last real lane. Returns True for a new player.

    Verified on a live match (2026-11-12): a few minutes in, m_nAssignedLane drops back to 0
    for everyone. That is not a lane swap, so a known lane is kept."""
    old = latest.get(p.account_id)
    if old is not None and p.lane is None and old.lane:
        p.lane = old.lane
    latest[p.account_id] = p
    return old is None


def watch_roster(api: DeadlockApi, match_id: int, account_id: int,
                 on_change: Callable[[Roster], None],
                 duration_s: float = 300, check_every_s: float = 3.0,
                 should_continue: Callable[[], bool] = lambda: True) -> None:
    """Call `on_change` whenever a hero, team or lane changes (lane swaps in the ~30 s prep
    window), until every lane is locked or `duration_s` runs out. The match was already
    spectated, so deadlock-api serves it from cache and this does not count against the
    spectate limit. In practice the Valve relay delay is longer than the swap window, so
    the first read is usually already locked and this returns right away."""
    latest: dict[int, Player] = {}
    last_sig = None
    last_check = time.time()
    end = time.time() + duration_s
    try:
        for event, data in api.stream_sse("/v1/matches/demo/live/query",
                                          {"match_id": match_id, "query": ROSTER_SQL}, timeout=60):
            if event in ("error", "end") or not should_continue() or time.time() > end:
                break
            p = _row_to_player(data)
            if p is not None:
                _merge(latest, p)
            if time.time() - last_check < check_every_s or len(latest) < 12:
                continue
            last_check = time.time()
            # lane_locked too: lanes often lock without any swap, and the page must learn that
            sig = tuple(sorted((x.account_id, x.hero_id, x.team, x.lane, x.lane_locked)
                               for x in latest.values()))
            if sig == last_sig:
                continue
            last_sig = sig
            # the first snapshot is reported too: it may already differ from the initial read.
            # The caller decides whether anything relevant (its lane) changed.
            try:
                roster = _build_roster(match_id, list(latest.values()), account_id)
                on_change(roster)
            except ApiError:
                continue
            if roster.lanes_locked:
                break  # lanes are final from here on
    except (ApiError, OSError):
        pass  # best effort: the first recommendation is already on screen


def fetch_roster(api: DeadlockApi, match_id: int, account_id: int,
                 on_status: Callable[[str], None] = lambda s: None,
                 max_wait_s: float = 600) -> Roster:
    """Try cheap path first, then the live broadcast, retrying while the match warms up."""
    deadline = time.time() + max_wait_s
    attempt = 0
    last_err: Exception | None = None
    while time.time() < deadline:
        attempt += 1
        active = roster_from_active(api, match_id, account_id)
        if active and len(active.players) >= 8:
            on_status("Jogadores encontrados na lista de partidas ativas.")
            # active list has no lanes; still try broadcast for lanes, but keep this as fallback
            try:
                return roster_from_broadcast(api, match_id, account_id, on_status)
            except ApiError:
                return active
        try:
            return roster_from_broadcast(api, match_id, account_id, on_status)
        except ApiError as e:
            last_err = e
            on_status(f"Tentativa {attempt}: {e} — tentando de novo em breve…")
            time.sleep(min(60, 15 * attempt))
    raise ApiError(f"Não foi possível ler os jogadores da partida: {last_err}")


# --------------------------------------------------------------------------- enemy items
# m_vecUpgrades is List(Binary): one 8-byte blob per item, the item id as little-endian
# uint32 in the first 4 bytes (the other 4 were always zero). Verified on a live match.
ITEMS_SQL = (
    'SELECT "m_steamID", "m_PlayerDataGlobal__m_vecUpgrades" AS upgrades '
    "FROM CCitadelPlayerController "
    'WHERE "m_PlayerDataGlobal__m_nHeroID" > 0'
)


def decode_upgrades(blobs) -> list[int]:
    out = []
    for blob in blobs or []:
        try:
            raw = bytes.fromhex(blob) if isinstance(blob, str) else bytes(blob)
        except (TypeError, ValueError):
            continue
        if len(raw) >= 4:
            out.append(int.from_bytes(raw[:4], "little"))
    return out


def snapshot_items(api: DeadlockApi, match_id: int, players: int = 12,
                   timeout_s: float = 45) -> dict[int, list[int]]:
    """account_id -> item ids, from one pass over the broadcast.

    The live query streams every row of every tick (~13 MB/min with this column) and does
    not filter on `tick`, so instead of keeping it open we read one full set of players
    and disconnect. The match is already spectated, so reconnecting is cheap (2-5 s) and
    does not count against the spectate limit.
    """
    seen: dict[int, list[int]] = {}
    start = time.time()
    for event, data in api.stream_sse("/v1/matches/demo/live/query",
                                      {"match_id": match_id, "query": ITEMS_SQL}, timeout=timeout_s):
        if event == "error":
            raise ApiError((data.get("error") if isinstance(data, dict) else str(data)) or "erro no live query")
        if event == "end" or time.time() - start > timeout_s:
            break
        if isinstance(data, dict) and "upgrades" in data:
            sid = int(data.get("m_steamID") or 0)
            if sid > STEAM64_BASE:
                seen[sid - STEAM64_BASE] = decode_upgrades(data["upgrades"])
            if len(seen) >= players:
                break
    return seen
