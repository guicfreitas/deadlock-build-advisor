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


UPGRADE_ITEMS = [
    {"id": 1, "name": "Boots", "class_name": "boots", "shopable": True, "item_tier": 1, "cost": 800, "item_slot_type": "vitality"},
    {"id": 2, "name": "Speed", "class_name": "speed", "shopable": True, "item_tier": 2, "cost": 1600,
     "item_slot_type": "vitality", "component_items": ["boots"]},
    {"id": 3, "name": "Rounds", "class_name": "rounds", "shopable": True, "item_tier": 1, "cost": 800, "item_slot_type": "weapon"},
    {"id": 4, "name": "Opening", "class_name": "opening", "shopable": True, "item_tier": 2, "cost": 1600,
     "item_slot_type": "weapon", "component_items": ["rounds"]},
    {"id": 5, "name": "Fortitude", "class_name": "fort", "shopable": True, "item_tier": 3, "cost": 3200,
     "item_slot_type": "vitality", "component_items": ["health"]},
    {"id": 6, "name": "Health", "class_name": "health", "shopable": True, "item_tier": 1, "cost": 800, "item_slot_type": "vitality"},
]


def test_lane_build_shows_tier1_components_before_their_upgrades():
    # feedback from a real match: Enduring Speed showed up with no Sprint Boots before it
    r = Recommender(api=None, catalog=Catalog(HEROES, UPGRADE_ITEMS), cfg=EngineConfig(min_matches=10))
    r.cfg.lane_budget = 3200
    base = [row(2, 560, 1000, 400), row(3, 510, 1000, 100), row(4, 550, 1000, 300)]
    s = r.score_items(base, base)
    lane = r.pick_lane(s)
    # Rounds is not picked on its own: it is Opening's first step
    assert {x.item_id for x in lane} == {2, 4}
    views = [r.cat.item_view(x) for x in lane]
    mid = [r.cat.bare_item_view(5)]
    r.with_components([views, mid], s)
    assert [v["name"] for v in views] == ["Rounds", "Opening", "Boots", "Speed"]
    assert views[0]["upgrades_to"] == "Opening" and views[2]["upgrades_to"] == "Speed"
    assert views[1]["upgrade_cost"] == 800 and "wr" not in views[2]
    assert r.spent(views) == 3200
    assert [v["name"] for v in mid] == ["Health", "Fortitude"]
