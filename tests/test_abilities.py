from deadlock_advisor import abilities as ab
from deadlock_advisor import gamebuild as g
from deadlock_advisor.engine import Catalog, EngineConfig, Recommender

A, B, C, D = 11, 22, 33, 44


def node(path, wins, matches, t=60.0):
    return {"abilities": list(path), "wins": wins, "losses": matches - wins, "matches": matches,
            "avg_upgrade_time_s": t}


def test_follows_the_crowd_unless_a_common_branch_wins_more():
    nodes = [node([A], 5000, 10000), node([B], 2000, 3000),           # B: 30% of A's players, +16.7pp
             node([B, B], 1500, 2800), node([B, C], 100, 150)]       # [B, C]: 5% share -> ignored
    steps = ab.pick_order(nodes)
    assert [s.ability_id for s in steps[:2]] == [B, B]
    assert steps[0].tier == 0 and steps[1].tier == 1


def test_rare_branch_never_wins_on_win_rate_alone():
    nodes = [node([A], 5000, 10000), node([B], 1900, 2000)]           # B wins 95% but 20% share
    assert ab.pick_order(nodes)[0].ability_id == A


def test_survivorship_does_not_leak_between_depths():
    # deeper nodes win more (winners level faster); siblings are compared only to each other
    nodes = [node([A], 5000, 10000), node([A, A], 3000, 5000), node([A, B], 2600, 4800)]
    assert [s.ability_id for s in ab.pick_order(nodes)][:2] == [A, A]


def test_complete_maxes_every_unlocked_ability():
    nodes = [node([A], 50, 100), node([A, B], 50, 100), node([A, B, A], 50, 100)]
    steps = ab.pick_order(nodes)
    assert len(steps) == 2 * (1 + ab.MAX_TIER)
    assert [(s.ability_id, s.tier) for s in steps[3:5]] == [(A, 2), (A, 3)]  # most invested first
    assert all(s.wr is None for s in steps[3:])


def test_empty_tree():
    assert ab.pick_order([]) == []


class FakeApi:
    def __init__(self, nodes, fail_first=False):
        self.nodes, self.fail_first, self.calls = nodes, fail_first, []

    def ability_order_tree(self, days=14, **params):
        self.calls.append(days)
        if self.fail_first and len(self.calls) == 1:
            raise RuntimeError("504")
        return self.nodes

    def ability(self, aid):
        return {"name": f"ab{aid}", "class_name": f"c{aid}", "image_webp": f"{aid}.webp"}


HERO = {"id": 1, "name": "X", "items": {"signature1": "c33", "signature2": "c11", "signature3": "c22",
                                        "signature4": "c44"}}


def test_recommender_ability_order_uses_game_keys_and_falls_back():
    nodes = [node(p, 50, 100) for p in ([A], [A, B], [A, B, C], [A, B, C, D])]
    api = FakeApi(nodes, fail_first=True)
    r = Recommender(api, Catalog([HERO], []), EngineConfig())
    out = r.ability_order(1, {"game_mode": "normal"})
    assert api.calls == [14, 7]                       # first query fails; shorter window retried
    assert [a["slot"] for a in out["abilities"]] == [1, 2, 3, 4]
    assert [s["slot"] for s in out["steps"][:4]] == [2, 3, 1, 4]   # A is key 2, B key 3, C key 1
    assert len(out["steps"]) == 16 and "wr" not in out


def test_ability_order_failure_is_not_fatal():
    class Broken(FakeApi):
        def ability_order_tree(self, **kw):
            raise RuntimeError("down")
    assert Recommender(Broken([]), Catalog([HERO], []), EngineConfig()).ability_order(1, {}) is None


def test_share_code_carries_the_ability_order():
    steps = [{"id": a} for a in (A, B, A, A, A, C, D)]
    rec = {"hero": {"id": 1, "name": "X"}, "lane_build": [{"id": 5}], "full_build": {},
           "ability_order": {"steps": steps}}
    b = g.from_recommendation(rec)
    assert b.ability_order[:3] == [(A, g.UNLOCK, -1), (B, g.UNLOCK, -1), (A, g.UPGRADE, -1)]
    assert len(b.ability_order) == 7
    assert g.from_recommendation(rec | {"ability_order": None}).ability_order == []
