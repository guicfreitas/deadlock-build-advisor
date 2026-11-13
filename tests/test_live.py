from deadlock_advisor.live import STEAM64_BASE, roster_from_broadcast, watch_roster

ME = 157672295


def row(aid, hero, team, lane):
    return {"tick": 1, "m_steamID": STEAM64_BASE + aid, "m_iTeamNum": team,
            "m_nAssignedLane": lane, "hero_id": hero}


# The real match 135914274 (2026-11-12): me = Infernus (1) in lane 6 vs Graves (76) + Paige (67).
LOBBY = [
    row(ME, 1, 2, 6), row(2, 72, 2, 1), row(3, 2, 2, 1), row(4, 77, 2, 4), row(5, 81, 2, 4), row(6, 99, 2, 6),
    row(7, 63, 3, 1), row(8, 31, 3, 1), row(9, 19, 3, 4), row(10, 66, 3, 4), row(11, 76, 3, 6),
    row(12, 67, 3, 4),  # Paige starts in lane 4 ...
]
SWAP = [row(12, 67, 3, 6), row(10, 66, 3, 1)]  # ... then swaps into my lane


class FakeApi:
    def __init__(self, rows):
        self.rows = rows

    def stream_sse(self, path, params, timeout=0):
        for r in self.rows:
            yield ("message", r) if r != "ping" else ("ping", None)
        yield "end", {}


def test_broadcast_roster_maps_teams_and_lanes():
    r = roster_from_broadcast(FakeApi(LOBBY), 1, ME, settle_s=0)
    assert r.game_mode == "normal"
    assert {p.team for p in r.players} == {0, 1}
    assert [p.hero_id for p in r.lane_enemies] == [76]


def test_watch_roster_reports_lane_swap():
    seen = []
    watch_roster(FakeApi(LOBBY + SWAP + ["ping"]), 1, ME, seen.append, check_every_s=0)
    assert seen, "expected at least one roster update"
    assert sorted(p.hero_id for p in seen[-1].lane_enemies) == [67, 76]


def test_lane_reset_to_zero_keeps_the_known_lane():
    # seen on a live match: a few minutes in m_nAssignedLane drops to 0 for everyone
    from deadlock_advisor.live import _merge, _row_to_player
    row = lambda lane, locked=True: {"m_steamID": 76561197960265728 + 7, "m_iTeamNum": 2,
                                     "m_nAssignedLane": lane, "m_bLaneSwapLocked": locked, "hero_id": 6}
    latest = {}
    assert _merge(latest, _row_to_player(row(4, False)))
    assert latest[7].lane == 4 and not latest[7].lane_locked
    assert not _merge(latest, _row_to_player(row(0)))
    assert latest[7].lane == 4 and latest[7].lane_locked
    _merge(latest, _row_to_player(row(6)))          # a real swap still goes through
    assert latest[7].lane == 6


def test_roster_lanes_locked():
    from deadlock_advisor.live import Player, _build_roster
    players = [Player(i, 1, i % 2, (1, 4, 6)[i % 3], lane_locked=i != 3) for i in range(12)]
    assert not _build_roster(1, players, 0).lanes_locked
    players[3].lane_locked = True
    assert _build_roster(1, players, 0).lanes_locked


def test_watch_roster_reports_lanes_locking_without_a_swap():
    # match 136381678 (2026-11-12): lanes locked with no swap, and the page never learned it
    locked = [dict(r, m_bLaneSwapLocked=True) for r in LOBBY]
    seen = []
    watch_roster(FakeApi(LOBBY + locked + ["ping"]), 1, ME, seen.append, check_every_s=0)
    assert seen and seen[-1].lanes_locked
    assert not seen[0].lanes_locked


def test_relay_status_is_translated():
    from deadlock_advisor.live import status_pt
    msg = "Broadcast relay not ready yet (attempt 4: Valve relay: Broadcast not ready), retrying..."
    assert "Valve" in status_pt(msg) and "attempt" not in status_pt(msg)
    assert status_pt("Jogadores encontrados") == "Jogadores encontrados"
