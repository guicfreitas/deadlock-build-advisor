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
