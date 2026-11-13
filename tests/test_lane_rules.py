from deadlock_advisor import config
from deadlock_advisor.app import Advisor
from deadlock_advisor.engine import Catalog, EngineConfig, Recommender

ITEMS = [
    {"id": 1, "name": "Extra Regen", "class_name": "upgrade_regen", "shopable": True, "item_tier": 1, "cost": 800, "item_slot_type": "vitality"},
    {"id": 2, "name": "Suppressor", "class_name": "upgrade_suppressor", "shopable": True, "item_tier": 2, "cost": 1600, "item_slot_type": "spirit"},
    {"id": 3, "name": "Rusted Barrel", "class_name": "upgrade_withering_whip", "shopable": True, "item_tier": 1, "cost": 800, "item_slot_type": "spirit"},
    {"id": 4, "name": "Fortitude", "class_name": "upgrade_fort", "shopable": True, "item_tier": 2, "cost": 1600, "item_slot_type": "vitality"},
    {"id": 5, "name": "Colossus", "class_name": "upgrade_colossus", "shopable": True, "item_tier": 3, "cost": 3200,
     "item_slot_type": "vitality", "component_items": ["upgrade_regen"]},
    {"id": 6, "name": "Late Gun", "class_name": "upgrade_gun", "shopable": True, "item_tier": 3, "cost": 3200, "item_slot_type": "weapon"},
]
HEROES = [{"id": 1, "name": "Infernus", "class_name": "hero_inferno"}, {"id": 13, "name": "Haze", "class_name": "hero_haze"},
          {"id": 4, "name": "Lady Geist", "class_name": "hero_geist"}, {"id": 3, "name": "Vindicta", "class_name": "hero_vindicta"}]


def row(iid, wins, matches, buy=300):
    return {"item_id": iid, "wins": wins, "losses": matches - wins, "matches": matches, "avg_buy_time_s": buy}


def make():
    return Recommender(api=None, catalog=Catalog(HEROES, ITEMS), cfg=EngineConfig(min_matches=10))


def scores(r):
    base = [row(i, 500, 1000) for i in (1, 2, 3, 4, 5, 6)]
    return r.score_items(base, base)


def test_gun_hero_in_lane_forces_suppressor_even_if_stats_rank_it_low():
    r = make()
    s = scores(r)
    s[2].score = -1  # the stats alone would never pick it
    forced = r.lane_forced([13], s)
    assert list(forced) == [2] and "Haze" in forced[2]
    lane = r.pick_lane(s, tuple(forced))
    assert 2 in [x.item_id for x in lane]


def test_two_gun_heroes_add_rusted_barrel_and_no_gun_hero_adds_nothing():
    r = make()
    s = scores(r)
    assert set(r.lane_forced([13, 3], s)) == {2, 3}
    assert r.lane_forced([4], s) == {}
    assert r.lane_forced([], s) == {}


def test_missing_suppressor_stats_fall_back_to_rusted_barrel():
    r = make()
    s = scores(r)
    del s[2]
    assert list(r.lane_forced([13], s)) == [3]


def test_lane_counters_and_lone_tier1_items_are_sold_but_components_are_not():
    r = make()
    s = scores(r)
    lane = [s[1], s[2], s[3], s[4]]           # Extra Regen is a component of Colossus (not in the lane)
    sold = r.lane_sell(lane, {2: "why"})
    assert sold == {1, 2, 3} or sold == {2, 3, 1}
    lane_with_colossus = [s[1], s[5]]
    assert r.lane_sell(lane_with_colossus, {}) == set()  # consumed by its upgrade, not sold


def test_sold_lane_items_free_slots_for_the_late_game():
    r = make()
    r.cfg.total_slots = 2
    base = [row(i, 500, 1000, buy=1800) for i in (3, 4, 5, 6)]   # bought late, so they are mid/late picks
    s = r.score_items(base, base)
    lane = [s[3], s[4]]
    assert r.pick_full(s, lane, sold=set()) == {"early": lane, "mid": [], "late": []}
    freed = r.pick_full(s, lane, sold={3})
    assert [x.item_id for x in freed["mid"] + freed["late"]] != []


def test_rank_default_is_archon_and_zero_means_all_ranks():
    cfg = config.Config()
    adv = Advisor.__new__(Advisor)
    adv.cfg = cfg
    assert adv._engine_config().filters == {"min_average_badge": 71}
    cfg.engine = {"filters": {}}                      # an old settings file must not drop the default
    assert adv._engine_config().filters == {"min_average_badge": 71}
    cfg.engine = {"filters": {"min_average_badge": 0}}
    assert adv._engine_config().filters == {"min_average_badge": 0}
    view = config.settings_view(config.Config())
    assert view["effective"]["engine.filters.min_average_badge"] == 71
