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
from .i18n import t


@dataclass
class EngineConfig:
    lane_window_s: int = 600          # what counts as "laning phase"
    lane_budget: int = 5600           # souls you can expect to spend in that window
    lane_max_items: int = 6
    total_slots: int = 12
    mid_items: int = 4                # picks reserved for the mid game before late fills the rest
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
        return self.heroes.get(hid, {}).get("name") or t("msg.hero_fallback", id=hid)

    def hero_view(self, hid: int) -> dict:
        h = self.heroes.get(hid, {})
        img = (h.get("images") or {})
        return {"id": hid, "name": self.hero_name(hid),
                "image": img.get("icon_image_small_webp") or img.get("icon_image_small")}

    def components(self, iid: int) -> list[int]:
        """Shop items this one is upgraded from (consumed when you buy it)."""
        i = self.items.get(iid) or {}
        return [self.by_class[c]["id"] for c in (i.get("component_items") or [])
                if c in self.by_class and self.by_class[c]["id"] in self.items]

    def bare_item_view(self, iid: int) -> dict:
        """An item without stats for this hero (e.g. a component nobody keeps for long)."""
        i = self.items[iid]
        return {
            "id": iid, "name": i["name"], "tier": i["item_tier"], "cost": i["cost"],
            "slot": i["item_slot_type"], "active": bool(i.get("is_active_item")),
            "image": i.get("shop_image_webp") or i.get("image"),
            "components": self.components(iid),
        }

    def item_view(self, s: ItemScore) -> dict:
        return self.bare_item_view(s.item_id) | {
            "wr": round(s.wr * 100, 1), "base_wr": round(s.base_wr * 100, 1),
            "lift": round(s.lift * 100, 1), "pop": round(s.rel_pop * 100),
            "matches": s.matches, "avg_buy_min": round(s.avg_buy_s / 60, 1),
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
        """Best items that fit the laning budget. An upgrade only costs what it adds on top
        of its components (the component is consumed), and a component of an item already
        picked is skipped: `with_components` puts it back in front of its upgrade."""
        c = self.cfg
        cands = sorted((s for s in scores.values() if self.cat.items[s.item_id]["item_tier"] <= 2),
                       key=lambda s: -s.score)
        chosen: list[ItemScore] = []
        budget = c.lane_budget
        for s in cands:
            if len(chosen) >= c.lane_max_items:
                break
            ids = {x.item_id for x in chosen}
            if any(s.item_id in self.cat.components(x) for x in ids):
                continue  # comes for free as the first step of an upgrade already picked
            comps = self.cat.components(s.item_id)
            cost = self.cat.items[s.item_id]["cost"] - sum(
                self.cat.items[x]["cost"] for x in comps if x in ids)
            if cost <= budget:
                chosen.append(s)
                budget -= cost
        return sorted(chosen, key=lambda s: s.avg_buy_s)

    def with_components(self, phases: list[list[dict]], scores: dict[int, ItemScore]) -> None:
        """Show how the build grows: put each upgrade's components (usually tier 1) right
        before it, unless already bought earlier, and mark them with `upgrades_to`.
        `upgrade_cost` is what the upgrade adds once its components are owned.
        Edits the item views in place, in build order (lane, mid, late)."""
        seen: dict[int, dict] = {}
        for items in phases:
            out: list[dict] = []
            for v in items:
                if v["id"] in seen:
                    continue  # already in the build as a component of an earlier upgrade
                owned = 0
                for cid in v.get("components", []):
                    comp = seen.get(cid)
                    # an earlier upgrade already consumed it (Fortitude and Colossus both
                    # take Extra Health): this upgrade needs a fresh one
                    if comp is None or "upgrades_to" in comp:
                        s = scores.get(cid)
                        comp = self.cat.item_view(s) if s else self.cat.bare_item_view(cid)
                        out.append(comp)
                        seen[cid] = comp
                    comp.setdefault("upgrades_to", v["name"])
                    owned += comp["cost"]
                if owned:
                    v["upgrade_cost"] = max(0, v["cost"] - owned)
                out.append(v)
                seen[v["id"]] = v
            items[:] = out

    @staticmethod
    def spent(items: list[dict]) -> int:
        """Souls spent on these items: an upgrade only adds its `upgrade_cost` when its
        components are in the same list (they are consumed into it)."""
        ids = {v["id"] for v in items}
        total = 0
        for v in items:
            if v.get("components") and all(c in ids for c in v["components"]):
                total += v.get("upgrade_cost", v["cost"])
            else:
                total += v["cost"]
        return total

    def held(self, ids: list[int]) -> list[int]:
        """The items that end up in the inventory: components are consumed by their upgrade."""
        consumed = {x for i in ids for x in self.cat.components(i)}
        return [i for i in ids if i not in consumed]

    def pick_full(self, scores: dict[int, ItemScore], lane: list[ItemScore]) -> dict[str, list[ItemScore]]:
        """Fill the inventory up to `total_slots`. Slots are counted on what is really held at
        the end: an upgrade of an item already in the build takes no new slot (a real match
        on 2026-11-12 ended with Graves' build two slots short of a full inventory)."""
        c = self.cfg
        taken = [s.item_id for s in lane]

        def phase(s: ItemScore) -> str:
            if s.avg_buy_s < c.mid_start_s:
                return "early"
            return "mid" if s.avg_buy_s < c.late_start_s else "late"

        def fits(iid: int) -> bool:
            after = self.held(taken + [iid])
            if len(after) > c.total_slots:
                return False
            st = self.cat.items[iid]["item_slot_type"]
            return sum(self.cat.items[i]["item_slot_type"] == st for i in after) <= c.max_per_slot_type

        cands = [s for s in sorted(scores.values(), key=lambda s: -s.score)
                 if phase(s) != "early" and self.cat.items[s.item_id]["item_tier"] >= 2]
        phases: dict[str, list[ItemScore]] = {"early": list(lane), "mid": [], "late": []}
        # mid gets its picks first so late items can't crowd it out, then late fills the
        # inventory, then anything left (mid or late) if late ran out of candidates
        for allowed, cap in ((("mid",), c.mid_items), (("late",), None), (("mid", "late"), None)):
            for s in cands:
                if len(self.held(taken)) >= c.total_slots:
                    break
                ph = phase(s)
                if ph not in allowed or s.item_id in taken or (cap is not None and len(phases[ph]) >= cap):
                    continue
                if any(s.item_id in self.cat.components(t) for t in taken):
                    continue  # already in the build as the first step of an upgrade
                if fits(s.item_id):
                    phases[ph].append(s)
                    taken.append(s.item_id)
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
                       "name": asset.get("name") or t("msg.ability_fallback", id=a),
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
        lane_views = [iv(s) for s in lane]
        full_views = {"early": lane_views, "mid": [iv(s) for s in phases["mid"]],
                      "late": [iv(s) for s in phases["late"]]}
        self.with_components([lane_views, full_views["mid"], full_views["late"]],
                             lane_scores | {k: v for k, v in full_scores.items() if k not in lane_scores})
        mu_lane, mu_all = res["mu_lane"], res["mu_all"]
        return {
            "hero": self.cat.hero_view(hero_id),
            "lane_enemies": [self.cat.hero_view(e) | {"matchup": mu_lane.get(e)} for e in lane_enemy_ids],
            "enemies": [self.cat.hero_view(e) | {"matchup": mu_all.get(e),
                                                 "counters": [iv(s) for s in counters.get(e, [])]}
                        for e in enemy_ids],
            "lane_build": lane_views,
            "lane_cost": self.spent(lane_views),
            "full_build": full_views,
            "ability_order": res["abilities"],
            "settings": {"lane_window_min": round(lw / 60, 1), "filters": f},
            # every scored item's lift vs this lobby (pp): lets mid-match counters pick the
            # best answer for this hero, not just any item that fits the threat
            "item_lift": {str(i): round(s.lift * 100, 2) for i, s in full_scores.items()},
        }
