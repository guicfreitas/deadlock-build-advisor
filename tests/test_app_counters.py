from deadlock_advisor import gamebuild
from deadlock_advisor.app import Advisor
from deadlock_advisor.config import Config
from deadlock_advisor.engine import Catalog
from deadlock_advisor.live import Player, Roster, decode_upgrades

ITEMS = [
    {"id": 1, "class_name": "upgrade_vampire", "name": "Bullet Lifesteal", "item_slot_type": "vitality", "item_tier": 2, "cost": 1600, "shopable": True},
    {"id": 2, "class_name": "upgrade_damage_recycler", "name": "Leech", "item_slot_type": "vitality", "item_tier": 4, "cost": 6400, "shopable": True},
    {"id": 3, "class_name": "upgrade_healbane", "name": "Healbane", "item_slot_type": "vitality", "item_tier": 2, "cost": 1600, "shopable": True},
    {"id": 5, "class_name": "upgrade_health", "name": "Extra Health", "item_slot_type": "vitality", "item_tier": 1, "cost": 800, "shopable": True},
    {"id": 6, "class_name": "upgrade_chonky", "name": "Fortitude", "item_slot_type": "vitality", "item_tier": 3, "cost": 3200, "shopable": True},
]
HEROES = [{"id": 79, "name": "Rem"}, {"id": 6, "name": "Abrams"}]


def _advisor(tmp_path):
    adv = Advisor(Config(cache_dir=str(tmp_path)))
    adv._catalog = Catalog(HEROES, ITEMS)
    me, enemy = Player(10, 79, 0, 1), Player(20, 6, 1, 1)
    adv._roster = Roster(1, [me, enemy], me)
    rec = {"hero": {"id": 79, "name": "Rem"}, "lane_enemies": [], "enemies": [],
           "lane_build": [{"id": 5, "lift": 0.5}], "lane_cost": 800,
           "full_build": {"mid": [{"id": 6, "lift": 1.0}], "late": []},
           "item_lift": {"3": 2.0, "5": 0.5, "6": 1.0}}
    adv.state.update(recommendation=rec)
    return adv, rec


def test_decode_upgrades_blob():
    assert decode_upgrades(["49da323c00000000", "zz", None]) == [0x3C32DA49]


def test_counters_compare_against_the_copied_build(tmp_path):
    adv, rec = _advisor(tmp_path)
    live = adv.update_counters({10: [], 20: [1, 2]})       # Abrams: lifesteal + Leech
    assert not live["against_copied"]
    s = live["suggestions"][0]
    assert s["buy"]["name"] == "Healbane" and s["instead_of"]["name"] == "Extra Health"

    adv.mark_copied(gamebuild.from_recommendation(rec, 10))
    assert adv.state.snapshot()["copied"]["name"].startswith("Advisor: Rem")
    live = adv.update_counters({10: [5], 20: [1, 2]})      # Extra Health already bought
    assert live["against_copied"]
    assert live["suggestions"][0]["instead_of"]["name"] == "Fortitude"
    assert adv.state.snapshot()["live_items"]["enemies"][0]["hero"]["name"] == "Abrams"


def test_copy_waits_for_final_lanes(tmp_path, monkeypatch):
    # match 136437146: the build was copied 1 s before a lane swap changed it
    import deadlock_advisor.app as app_mod
    adv, _ = _advisor(tmp_path)
    me = Player(10, 79, 0, 1)
    roster = Roster(1, [me, Player(20, 6, 1, 1)], me)
    adv._current_job = 1
    monkeypatch.setattr(adv, "compute", lambda *a, **k: None)
    adv._apply_roster(roster, "ok")
    assert adv.copy_blocked()  # lanes still open

    seen = {}
    def fake_watch(api, match_id, account, on_change, **kw):
        seen["blocked_while_watching"] = adv.copy_blocked()
    monkeypatch.setattr(app_mod, "watch_roster", fake_watch)
    adv._watch_lanes(1, 10, roster)  # the watch gives up without every lane locked
    assert seen["blocked_while_watching"] and adv.copy_blocked() is None


def test_copy_allowed_without_a_live_roster(tmp_path):
    adv, _ = _advisor(tmp_path)  # manual mode: no roster in the state
    assert adv.copy_blocked() is None
