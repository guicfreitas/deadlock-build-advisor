"""Mid-match counters: react to what the enemies actually bought.

The stats API can condition on enemy *heroes* but not on enemy *items*, so this is a rule
layer on top of the data: enemy purchases are grouped into threats (healing, weapon damage,
spirit damage, crowd control, resistances), and each threat has known answers. Among the
answers, the data picks: we suggest the one with the best win rate lift for this hero
against this lobby (Recommender's per-item lift), and swap it in for the weakest item of
the build that the player has not bought yet.

Items are keyed by class_name: it is stable across patches and client languages.
"""
from __future__ import annotations

from dataclasses import dataclass

TIER_WEIGHT = {1: 0.5, 2: 1.0, 3: 2.0, 4: 3.0, 5: 3.0}
SUGGEST_AT = 3.0      # threat strength needed before suggesting anything (e.g. one T4, or T3 + T2)
MAX_SUGGESTIONS = 3
# Late game everyone owns T3+ weapon and spirit items, so both damage threats always fire.
# Only answer the dominant damage type, plus the other one if it is nearly as strong.
DAMAGE_KEYS = ("weapon", "spirit")
DAMAGE_RATIO = 0.7
MAX_SOURCES_PER_ENEMY = 2


@dataclass(frozen=True)
class Threat:
    key: str
    label: str                    # pt-BR, shown to the player
    triggers: frozenset[str]      # enemy items that create it
    answers: tuple[str, ...]      # items that counter it
    slot: str | None = None       # any enemy item of this slot and tier >= 3 also counts


def _t(key, label, triggers, answers, slot=None) -> Threat:
    return Threat(key, label, frozenset(triggers), tuple(answers), slot)


THREATS = (
    _t("healing", "cura e roubo de vida",
       ["upgrade_vampire", "upgrade_health_stealing_magic", "upgrade_lifestrike_gauntlets",
        "upgrade_boxing_glove", "upgrade_healing_booster", "upgrade_resonant_healing",
        "upgrade_health_nova", "upgrade_damage_recycler", "upgrade_siphon_bullets",
        "upgrade_healbuff", "upgrade_surging_power", "upgrade_restorative_locket",
        "upgrade_rescue_beam", "upgrade_medic_bullets", "upgrade_infuser"],
       ["upgrade_healbane", "upgrade_toxic_bullets", "upgrade_rupture", "upgrade_inhibitor"]),
    _t("weapon", "dano de arma",
       ["upgrade_aprounds", "upgrade_glass_cannon", "upgrade_critshot", "upgrade_fervor",
        "upgrade_ricochet", "upgrade_infinite_rounds", "upgrade_crushing_fists"],
       ["upgrade_regenerating_bullet_shield", "upgrade_return_fire", "upgrade_weapon_shielding",
        "upgrade_improved_bullet_armor", "upgrade_metal_skin", "upgrade_deflecting_armor"],
       slot="weapon"),
    _t("spirit", "dano espiritual",
       ["upgrade_magic_storm", "upgrade_ultimate_burst", "upgrade_boundless_spirit",
        "upgrade_mystic_reverb", "upgrade_spirit_burn", "upgrade_ethereal_bullets"],
       ["upgrade_spirit_bubble", "upgrade_tech_purge", "upgrade_counterspell",
        "upgrade_absorbing_armor", "upgrade_diviners_kevlar", "upgrade_spellbreaker"],
       slot="spirit"),
    _t("control", "controle (stun, silêncio, lentidão)",
       ["upgrade_target_stun", "upgrade_targeted_silence", "upgrade_containment",
        "upgrade_greater_withering_whip", "upgrade_glitch", "upgrade_aoe_root",
        "upgrade_proc_silence", "upgrade_banshee_slugs", "upgrade_arctic_blast",
        "upgrade_shrink_ray", "upgrade_shivas_bracelet"],
       ["upgrade_debuff_reducer", "upgrade_reduce_debuff_duration", "upgrade_auto_cleanse",
        "upgrade_unstoppable"]),
    _t("bullet_armor", "resistência a balas",
       ["upgrade_improved_bullet_armor", "upgrade_metal_skin", "upgrade_deflecting_armor",
        "upgrade_regenerating_bullet_shield", "upgrade_juggernaut"],
       ["upgrade_bullet_resist_shredder", "upgrade_bullet_armor_reduction_aura",
        "upgrade_bulletshredimbue"]),
    _t("spirit_armor", "resistência espiritual",
       ["upgrade_tech_purge", "upgrade_absorbing_armor", "upgrade_diviners_kevlar",
        "upgrade_spirit_bubble", "upgrade_counterspell"],
       ["upgrade_magic_vulnerability", "upgrade_tech_defense_shredders",
        "upgrade_escalating_exposure"]),
)


@dataclass
class ThreatHit:
    threat: Threat
    strength: float
    sources: list[tuple[int, int]]   # (enemy hero_id, item_id) that created it


def find_threats(enemy_items: dict[int, list[int]], items: dict[int, dict]) -> list[ThreatHit]:
    """enemy_items: hero_id -> item ids that enemy owns. Strongest threat first.

    The weaker damage threat is dropped unless it is at least DAMAGE_RATIO of the stronger."""
    hits = []
    for th in THREATS:
        strength, sources = 0.0, []
        for hero, owned in enemy_items.items():
            for iid in owned:
                it = items.get(iid)
                if not it:
                    continue
                named = it.get("class_name") in th.triggers
                by_slot = th.slot and it.get("item_slot_type") == th.slot and it.get("item_tier", 0) >= 3
                if named or by_slot:
                    strength += TIER_WEIGHT.get(it.get("item_tier", 1), 1.0)
                    sources.append((hero, iid))
        if strength:
            hits.append(ThreatHit(th, strength, sources))
    damage = [h for h in hits if h.threat.key in DAMAGE_KEYS]
    if len(damage) == 2:
        weak, strong = sorted(damage, key=lambda h: h.strength)
        if weak.strength < DAMAGE_RATIO * strong.strength:
            hits.remove(weak)
    return sorted(hits, key=lambda h: -h.strength)


def suggest(enemy_items: dict[int, list[int]], my_items: list[int], planned: list[int],
            items: dict[int, dict], lift: dict[int, float], hero_names: dict[int, str]) -> list[dict]:
    """Swap suggestions: "buy <answer> instead of <planned item>, because <enemy> bought ...".

    planned: the build the player is following (the copied build, in order). Items already
    owned are never suggested nor replaced. lift: item_id -> win rate lift (pp) for this
    hero in this lobby; unknown items count as 0.
    """
    by_class = {it.get("class_name"): iid for iid, it in items.items()}
    owned = set(my_items)
    remaining = [i for i in planned if i not in owned]
    taken = owned | set(planned)
    out = []
    for hit in find_threats(enemy_items, items):
        if hit.strength < SUGGEST_AT or len(out) >= MAX_SUGGESTIONS:
            continue
        answers = [by_class[c] for c in hit.threat.answers if c in by_class]
        if any(a in taken for a in answers):
            continue  # the player already has (or plans) an answer to this
        answer = max(answers, key=lambda a: lift.get(a, 0.0), default=None)
        if answer is None:
            continue
        # Replace the weakest not-yet-bought item of the same slot; on a tie, the one furthest
        # down the build (least committed). No same-slot item left -> "buy it as well".
        slot = items[answer].get("item_slot_type")
        pool = [i for i in remaining if items.get(i, {}).get("item_slot_type") == slot]
        replace = min(pool, key=lambda i: (lift.get(i, 0.0), -remaining.index(i)), default=None)
        if replace is not None:
            remaining.remove(replace)
        taken.add(answer)
        by_enemy: dict[int, list[int]] = {}
        for hero, iid in hit.sources:
            by_enemy.setdefault(hero, []).append(iid)
        by_enemy = {h: [items[i]["name"] for i in sorted(ids, key=lambda i: -items[i].get("item_tier", 0))
                        [:MAX_SOURCES_PER_ENEMY]] for h, ids in by_enemy.items()}
        reason = "; ".join(f"{hero_names.get(h, h)} comprou {', '.join(n)}" for h, n in by_enemy.items())
        out.append({
            "threat": hit.threat.key, "threat_label": hit.threat.label,
            "strength": round(hit.strength, 1),
            "buy": answer, "instead_of": replace,
            "lift": round(lift.get(answer, 0.0), 1),
            "reason": reason,
        })
    return out
