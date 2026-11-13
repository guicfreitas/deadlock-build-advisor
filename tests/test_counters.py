from deadlock_advisor import counters

ITEMS = {
    1: {"class_name": "upgrade_vampire", "name": "Bullet Lifesteal", "item_slot_type": "vitality", "item_tier": 2},
    2: {"class_name": "upgrade_damage_recycler", "name": "Leech", "item_slot_type": "vitality", "item_tier": 4},
    3: {"class_name": "upgrade_healbane", "name": "Healbane", "item_slot_type": "vitality", "item_tier": 2},
    4: {"class_name": "upgrade_toxic_bullets", "name": "Toxic Bullets", "item_slot_type": "weapon", "item_tier": 3},
    5: {"class_name": "upgrade_health", "name": "Extra Health", "item_slot_type": "vitality", "item_tier": 1},
    6: {"class_name": "upgrade_fortitude", "name": "Fortitude", "item_slot_type": "vitality", "item_tier": 3},
    7: {"class_name": "upgrade_magic_storm", "name": "Surge of Power", "item_slot_type": "spirit", "item_tier": 3},
    8: {"class_name": "upgrade_glass_cannon", "name": "Glass Cannon", "item_slot_type": "weapon", "item_tier": 4},
    9: {"class_name": "upgrade_burst_fire", "name": "Burst Fire", "item_slot_type": "weapon", "item_tier": 3},
    10: {"class_name": "upgrade_metal_skin", "name": "Metal Skin", "item_slot_type": "vitality", "item_tier": 3},
    11: {"class_name": "upgrade_spirit_bubble", "name": "Spirit Shielding", "item_slot_type": "vitality", "item_tier": 2},
}
NAMES = {100: "Abrams", 200: "Haze"}


def test_healing_threat_suggests_antiheal_instead_of_weakest_planned():
    enemy = {100: [1, 2]}             # lifesteal + Leech = 1 + 3 = strength 4
    lift = {3: 2.0, 4: 1.0, 5: -1.0, 6: 0.5}
    out = counters.suggest(enemy, my_items=[], planned=[6, 5], items=ITEMS, lift=lift, hero_names=NAMES)
    assert len(out) == 1
    s = out[0]
    assert s["threat"] == "healing" and s["buy"] == 3      # Healbane beats Toxic Bullets on lift
    assert s["instead_of"] == 5                            # weakest planned vitality item
    assert s["reason"] == "Abrams bought Leech, Bullet Lifesteal"


def test_weak_threats_and_existing_answers_are_ignored():
    assert counters.suggest({100: [1]}, [], [5], ITEMS, {}, NAMES) == []          # strength 1 < 3
    assert counters.suggest({100: [1, 2]}, [3], [5], ITEMS, {}, NAMES) == []      # already owns Healbane
    assert counters.suggest({100: [1, 2]}, [], [4, 5], ITEMS, {}, NAMES) == []    # Toxic Bullets planned


def test_no_same_slot_item_means_buy_as_well():
    out = counters.suggest({100: [1, 2]}, [], [7], ITEMS, {3: 1.0}, NAMES)        # plan has only spirit
    assert out[0]["buy"] == 3 and out[0]["instead_of"] is None


def test_only_the_dominant_damage_type_is_answered():
    enemy = {100: [8, 9], 200: [7]}   # weapon 3 + 2 = 5, spirit 2 -> spirit < 70% of weapon
    keys = [h.threat.key for h in counters.find_threats(enemy, ITEMS)]
    assert "weapon" in keys and "spirit" not in keys
    out = counters.suggest(enemy, [], [5, 6], ITEMS, {10: 1.5}, NAMES)
    assert [s["buy"] for s in out] == [10]                 # Metal Skin, the best-lift weapon answer
    assert out[0]["instead_of"] == 6                       # tie on lift -> furthest down the build
