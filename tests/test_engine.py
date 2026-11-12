from deadlock_advisor.engine import Catalog, EngineConfig, Recommender

ITEMS = [
    {"id": 1, "name": "A", "class_name": "a", "shopable": True, "item_tier": 1, "cost": 800, "item_slot_type": "weapon"},
    {"id": 2, "name": "B", "class_name": "b", "shopable": True, "item_tier": 1, "cost": 800, "item_slot_type": "vitality"},
    {"id": 3, "name": "C", "class_name": "c", "shopable": True, "item_tier": 2, "cost": 1600, "item_slot_type": "spirit"},
    {"id": 4, "name": "D", "class_name": "d", "shopable": True, "item_tier": 3, "cost": 3200, "item_slot_type": "weapon",
     "component_items": ["a"]},
    {"id": 5, "name": "Hidden", "class_name": "e", "shopable": False, "item_tier": 1, "cost": 800, "item_slot_type": "weapon"},
]
HEROES = [{"id": 1, "name": "Infernus"}, {"id": 6, "name": "Abrams"}]


def row(iid, wins, matches, buy=300):
    return {"item_id": iid, "wins": wins, "losses": matches - wins, "matches": matches, "avg_buy_time_s": buy}


def make():
    return Recommender(api=None, catalog=Catalog(HEROES, ITEMS), cfg=EngineConfig(min_matches=10))


def test_lift_rewards_matchup_specific_items():
    r = make()
    base = [row(1, 5000, 10000), row(2, 5000, 10000)]
    ctx = [row(1, 300, 500), row(2, 250, 500)]  # item 1 does much better vs this enemy
    s = r.score_items(ctx, base)
    assert s[1].lift > 0.03 > s[2].lift
    assert s[1].score > s[2].score


def test_smoothing_dampens_tiny_samples():
    r = make()
    r.cfg.min_rel_pop = 0
    base = [row(1, 500, 1000), row(2, 500, 1000)]
    ctx = [row(1, 15, 15), row(2, 600, 1000)]  # 100% WR on 15 games should not dominate
    s = r.score_items(ctx, base)
    assert s[1].lift < 0.05  # raw lift would be +50%


def test_unshopable_items_ignored_and_lane_budget():
    r = make()
    r.cfg.lane_budget = 1600
    base = [row(i, 520, 1000) for i in (1, 2, 3, 5)]
    s = r.score_items(base, base)
    assert 5 not in s
    lane = r.pick_lane(s)
    assert sum(ITEMS[x.item_id - 1]["cost"] for x in lane) <= 1600


def test_full_build_excludes_lane_items_and_tier1():
    r = make()
    base = [row(1, 520, 1000), row(2, 520, 1000), row(3, 540, 1000, 900), row(4, 560, 1000, 1800)]
    s = r.score_items(base, base)
    lane = r.pick_lane(s)
    phases = r.pick_full(s, lane)
    ids = [x.item_id for x in phases["mid"] + phases["late"]]
    assert not set(ids) & {x.item_id for x in lane}
    assert 4 in [x.item_id for x in phases["late"]]
