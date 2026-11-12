"""Build recommendation engine.

Idea: for the hero you are playing, compare how each item performs
  * in general (baseline), vs
  * in matches against the specific enemies you are facing.
The difference ("lift") is what makes an item a good answer to *this* lobby.

Win rates are smoothed (Bayesian prior = the item's baseline win rate) so that
items with few samples cannot jump to the top on noise.

Two builds are produced:
  * Lane build  -> items bought in the first `lane_window_s` seconds, conditioned on
                   your lane opponents only (same_lane_filter=true).
  * Full build  -> whole-game items, averaging the lift against every enemy hero,
                   split into early / mid / late by typical purchase time.
Plus per-enemy counter items and hero-vs-hero matchup win rates.
"""
from __future__ import annotations

import math
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import abilities
from .api import DeadlockApi


@dataclass
class EngineConfig:
    lane_window_s: int = 600          # what counts as "laning phase"
    lane_budget: int = 5600           # souls you can expect to spend in that window
    lane_max_items: int = 6
    total_slots: int = 12
    max_per_slot_type: int = 6
    prior_strength: float = 150.0     # pseudo-matches pulling WR toward the baseline
    lift_weight: float = 3.0          # how much matchup-specific lift matters
    pop_weight: float = 0.06          # how much popularity (proven picks) matters
    min_rel_pop: float = 0.04         # ignore items almost nobody buys
    min_matches: int = 40
    mid_start_s: int = 600
    late_start_s: int = 1500
    ability_min_rel_pop: float = 0.25  # ability order: a branch needs this share of the top one
    ability_pop_weight: float = 0.03   # ability order: bonus for the most used branch
    filters: dict = field(default_factory=dict)  # e.g. {"min_average_badge": 60}


@dataclass
class ItemScore:
    item_id: int
    wr: float           # smoothed win rate in the conditioned context
    base_wr: float      # smoothed baseline win rate
    lift: float
    rel_pop: float      # popularity relative to the most bought item
    matches: int
    avg_buy_s: float
    score: float


def _wr(row: dict) -> float:
    m = row.get("matches") or (row.get("wins", 0) + row.get("losses", 0))
    return row["wins"] / m if m else 0.5


def _smooth(wins: float, matches: float, prior: float, k: float) -> float:
    return (wins + k * prior) / (matches + k)


class Catalog:
    """Static game data (heroes / items) from the assets API."""

    def __init__(self, heroes: list[dict], items: list[dict]):
        self.heroes = {h["id"]: h for h in heroes if h.get("player_selectable", True)}
        self.items = {i["id"]: i for i in items
                      if i.get("shopable") and not i.get("disabled") and 1 <= (i.get("item_tier") or 0) <= 4}
        self.by_class = {i["class_name"]: i for i in items}

    def hero_name(self, hid: int) -> str:
        return self.heroes.get(hid, {}).get("name", f"Herói {hid}")

    def hero_view(self, hid: int) -> dict:
        h = self.heroes.get(hid, {})
        img = (h.get("images") or {})
        return {"id": hid, "name": self.hero_name(hid),
                "image": img.get("icon_image_small_webp") or img.get("icon_image_small")}

    def item_view(self, s: ItemScore) -> dict:
        i = self.items[s.item_id]
        comps = [self.by_class[c]["id"] for c in (i.get("component_items") or []) if c in self.by_class]
        return {
            "id": s.item_id, "name": i["name"], "tier": i["item_tier"], "cost": i["cost"],
            "slot": i["item_slot_type"], "active": bool(i.get("is_active_item")),
            "image": i.get("shop_image_webp") or i.get("image"),
            "wr": round(s.wr * 100, 1), "base_wr": round(s.base_wr * 100, 1),
            "lift": round(s.lift * 100, 1), "pop": round(s.rel_pop * 100),
            "matches": s.matches, "avg_buy_min": round(s.avg_buy_s / 60, 1),
            "components": comps,
        }


class Recommender:
    def __init__(self, api: DeadlockApi, catalog: Catalog, cfg: EngineConfig | None = None):
        self.api = api
        self.cat = catalog
        self.cfg = cfg or EngineConfig()

    # ----------------------------------------------------------- scoring
    def score_items(self, ctx_rows: list[dict], base_rows: list[dict]) -> dict[int, ItemScore]:
        c = self.cfg
        base = {r["item_id"]: r for r in base_rows}
        ctx = {r["item_id"]: r for r in ctx_rows if r["item_id"] in self.cat.items}
        if not ctx:
            return {}
        top = max(r["matches"] for r in ctx.values()) or 1
        # The hero's overall win-rate shift in this context (e.g. "Infernus loses 3% more vs Haze")
        # affects every item equally; remove it so lift measures the *item*, not the matchup.
        num = den = 0.0
        for iid, r in ctx.items():
            b = base.get(iid)
            if b and b["matches"] and r["matches"]:
                num += (_wr(r) - _wr(b)) * r["matches"]
                den += r["matches"]
        offset = num / den if den else 0.0
        out = {}
        for iid, r in ctx.items():
            if r["matches"] < c.min_matches:
                continue
            rel_pop = r["matches"] / top
            if rel_pop < c.min_rel_pop:
                continue
            b = base.get(iid)
            base_prior = _wr(b) if b else _wr(r)
            base_wr = _smooth(b["wins"], b["matches"], base_prior, c.prior_strength) if b else base_prior
            wr = _smooth(r["wins"], r["matches"], base_wr + offset, c.prior_strength)
            lift = wr - base_wr - offset
            score = (wr - 0.5) + c.lift_weight * lift + c.pop_weight * math.sqrt(rel_pop)
            out[iid] = ItemScore(iid, wr, base_wr, lift, rel_pop, r["matches"],
                                 float((b or r).get("avg_buy_time_s") or 0), score)
        return out

    @staticmethod
    def combine(per_enemy: list[dict[int, ItemScore]], base: dict[int, ItemScore], cfg: EngineConfig) -> dict[int, ItemScore]:
        """Average the lift of each item over all enemies, keep baseline popularity."""
        out = {}
        for iid, b in base.items():
            lifts = [m[iid].lift for m in per_enemy if iid in m]
            if not lifts:
                continue
            lift = sum(lifts) / len(per_enemy)  # missing data counts as zero lift
            wr = b.base_wr + lift
            score = (wr - 0.5) + cfg.lift_weight * lift + cfg.pop_weight * math.sqrt(b.rel_pop)
            out[iid] = ItemScore(iid, wr, b.base_wr, lift, b.rel_pop, b.matches, b.avg_buy_s, score)
        return out

    # ---------------------------------------------------------- selection
    def pick_lane(self, scores: dict[int, ItemScore]) -> list[ItemScore]:
        c = self.cfg
        cands = sorted((s for s in scores.values() if self.cat.items[s.item_id]["item_tier"] <= 2),
                       key=lambda s: -s.score)
        chosen, budget = [], c.lane_budget
        for s in cands:
            cost = self.cat.items[s.item_id]["cost"]
            if cost <= budget and len(chosen) < c.lane_max_items:
                chosen.append(s)
                budget -= cost
        return sorted(chosen, key=lambda s: s.avg_buy_s)

    def pick_full(self, scores: dict[int, ItemScore], lane: list[ItemScore]) -> dict[str, list[ItemScore]]:
        c = self.cfg
        taken = {s.item_id for s in lane}
        slot_count: dict[str, int] = {}
        for s in lane:
            st = self.cat.items[s.item_id]["item_slot_type"]
            slot_count[st] = slot_count.get(st, 0) + 1

        def phase(s: ItemScore) -> str:
            if s.avg_buy_s < c.mid_start_s:
                return "early"
            return "mid" if s.avg_buy_s < c.late_start_s else "late"

        quotas = {"mid": 4, "late": max(0, c.total_slots - len(lane) - 4)}
        phases: dict[str, list[ItemScore]] = {"early": list(lane), "mid": [], "late": []}
        for s in sorted(scores.values(), key=lambda s: -s.score):
            item = self.cat.items[s.item_id]
            ph = phase(s)
            if s.item_id in taken or ph == "early" or item["item_tier"] < 2:
                continue
            if len(phases[ph]) >= quotas[ph]:
                continue
            st = item["item_slot_type"]
            if slot_count.get(st, 0) >= c.max_per_slot_type:
                continue
            phases[ph].append(s)
            taken.add(s.item_id)
            slot_count[st] = slot_count.get(st, 0) + 1
        for k in ("mid", "late"):
            phases[k].sort(key=lambda s: s.avg_buy_s)
        return phases

    def counters(self, per_enemy: dict[int, dict[int, ItemScore]], n: int = 3) -> dict[int, list[ItemScore]]:
        out = {}
        for eid, scores in per_enemy.items():
            good = [s for s in scores.values()
                    if s.lift > 0 and s.rel_pop >= 0.08 and self.cat.items[s.item_id]["item_tier"] >= 2]
            out[eid] = sorted(good, key=lambda s: -s.lift)[:n]
        return out

    def matchups(self, hero_id: int, enemy_ids: list[int], same_lane: bool, filters: dict) -> dict[int, dict]:
        rows = self.api.hero_counter_stats(same_lane_filter=same_lane, min_matches=20, **filters)
        out = {}
        for r in rows:
            if r["hero_id"] == hero_id and r["enemy_hero_id"] in enemy_ids:
                mp = r["matches_played"] or 1
                out[r["enemy_hero_id"]] = {"wr": round(100 * r["wins"] / mp, 1), "matches": mp}
        return out

    def ability_order(self, hero_id: int, filters: dict) -> dict | None:
        """Recommended ability point order, or None when the API has nothing usable.
        Optional: a failure here must not cost the player the item build."""
        try:
            try:
                nodes = self.api.ability_order_tree(hero_id=hero_id, **filters)
            except Exception:  # noqa: BLE001 - heavy query; a shorter window is cheaper
                nodes = self.api.ability_order_tree(days=7, hero_id=hero_id, **filters)
            ocfg = abilities.OrderConfig(self.cfg.ability_min_rel_pop, self.cfg.ability_pop_weight,
                                         self.cfg.prior_strength)
            steps = abilities.pick_order(nodes, ocfg)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return None
        if not steps:
            return None
        info = {}
        for a in dict.fromkeys(s.ability_id for s in steps):
            try:
                asset = self.api.ability(a)
            except Exception:  # noqa: BLE001 - a missing name is cosmetic
                asset = {}
            info[a] = {"id": a, "class_name": asset.get("class_name"),
                       "name": asset.get("name") or f"Habilidade {a}",
                       "image": asset.get("image_webp") or asset.get("image")}
        # number abilities by their key in game (signature1..4), not by unlock order
        sig = (self.cat.heroes.get(hero_id) or {}).get("items") or {}
        key = {sig.get(f"signature{n}"): n for n in range(1, 5)}
        slot = {a: key.get(v["class_name"]) or n for n, (a, v) in enumerate(info.items(), 1)}
        for a, v in info.items():
            v["slot"] = slot[a]
        last = next((s for s in reversed(steps) if s.wr is not None), None)
        # no win rate on purpose: a full order's win rate is inflated by survivorship
        # (players who get that far are mostly in long, won games)
        return {
            "abilities": sorted(info.values(), key=lambda v: v["slot"]),
            "steps": [{"id": s.ability_id, "slot": slot[s.ability_id], "tier": s.tier, "cost": s.cost,
                       "avg_min": round(s.avg_time_s / 60, 1) if s.avg_time_s else None}
                      for s in steps],
            "matches": last.matches if last else 0,
        }

    # ------------------------------------------------------------ public
    def recommend(self, hero_id: int, enemy_ids: list[int], lane_enemy_ids: list[int]) -> dict:
        """Standard 6v6 map (casual/unranked and competitive/ranked).
        Street Brawl is not supported: items there are drafted, not bought."""
        c = self.cfg
        f = {"game_mode": "normal"} | c.filters
        same_lane = True
        lw = c.lane_window_s
        jobs = {
            "lane_base": lambda: self.api.item_stats(hero_id=hero_id, max_bought_at_s=lw, **f),
            "full_base": lambda: self.api.item_stats(hero_id=hero_id, **f),
            "mu_lane": lambda: self.matchups(hero_id, lane_enemy_ids, same_lane, f) if lane_enemy_ids else {},
            "mu_all": lambda: self.matchups(hero_id, enemy_ids, False, f),
            "abilities": lambda: self.ability_order(hero_id, f),
        }
        if lane_enemy_ids:
            jobs["lane_ctx"] = lambda: self.api.item_stats(
                hero_id=hero_id, enemy_hero_ids=lane_enemy_ids, same_lane_filter=same_lane,
                max_bought_at_s=lw, **f)
        for e in enemy_ids:
            jobs[f"vs_{e}"] = (lambda e=e: self.api.item_stats(hero_id=hero_id, enemy_hero_ids=[e], **f))
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {k: ex.submit(fn) for k, fn in jobs.items()}
            res = {k: fu.result() for k, fu in futs.items()}

        lane_scores = self.score_items(res.get("lane_ctx") or res["lane_base"], res["lane_base"])
        lane = self.pick_lane(lane_scores)

        full_base_scores = self.score_items(res["full_base"], res["full_base"])
        per_enemy = {e: self.score_items(res[f"vs_{e}"], res["full_base"]) for e in enemy_ids}
        full_scores = self.combine(list(per_enemy.values()), full_base_scores, c) if enemy_ids else full_base_scores
        phases = self.pick_full(full_scores, lane)
        counters = self.counters(per_enemy)

        iv = self.cat.item_view
        mu_lane, mu_all = res["mu_lane"], res["mu_all"]
        return {
            "hero": self.cat.hero_view(hero_id),
            "lane_enemies": [self.cat.hero_view(e) | {"matchup": mu_lane.get(e)} for e in lane_enemy_ids],
            "enemies": [self.cat.hero_view(e) | {"matchup": mu_all.get(e),
                                                 "counters": [iv(s) for s in counters.get(e, [])]}
                        for e in enemy_ids],
            "lane_build": [iv(s) for s in lane],
            "lane_cost": sum(self.cat.items[s.item_id]["cost"] for s in lane),
            "full_build": {k: [iv(s) for s in v] for k, v in phases.items()},
            "ability_order": res["abilities"],
            "settings": {"lane_window_min": round(lw / 60, 1), "filters": f},
            # every scored item's lift vs this lobby (pp): lets mid-match counters pick the
            # best answer for this hero, not just any item that fits the threat
            "item_lift": {str(i): round(s.lift * 100, 2) for i, s in full_scores.items()},
        }
