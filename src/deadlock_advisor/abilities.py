"""Ability upgrade order, picked from what players of the hero actually did.

Source: deadlock-api's /v1/analytics/ability-order-tree, one node per order prefix (every
ability point spent, unlocks included) with the wins/matches of every player whose order
starts with it. We walk it from the root, choosing one child per step.

Why not just "the highest win rate path": deeper prefixes win more because winners level
up faster (survivorship), so win rates are only compared between siblings, which share the
same depth and about the same game time. Within a step we follow the crowd and only take a
less common branch when enough players use it (min_rel_pop of the top sibling) and it wins
more by a margin that beats the popularity bonus.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

MAX_UNLOCKS = 4
MAX_TIER = 3          # each ability: unlock + 3 upgrades
UPGRADE_COSTS = (1, 2, 5)


@dataclass
class OrderConfig:
    min_rel_pop: float = 0.25    # a branch needs this share of the top sibling's players
    pop_weight: float = 0.03     # bonus for the most used branch (in win-rate units)
    prior_strength: float = 150.0


@dataclass
class Step:
    ability_id: int
    tier: int                    # 0 = unlock, 1..3 = upgrade tier
    wr: float | None             # smoothed win rate of the prefix ending here (None = filled in)
    matches: int
    avg_time_s: float | None

    @property
    def cost(self) -> int:
        return 1 if self.tier == 0 else UPGRADE_COSTS[self.tier - 1]


def _smooth(wins: float, matches: float, prior: float, k: float) -> float:
    return (wins + k * prior) / (matches + k)


def pick_order(nodes: list[dict], cfg: OrderConfig | None = None) -> list[Step]:
    """Greedy walk of the ability-order tree; returns one Step per ability point."""
    cfg = cfg or OrderConfig()
    children: dict[tuple, list[dict]] = {}
    for n in nodes:
        path = tuple(n.get("abilities") or ())
        if path and n.get("matches"):
            children.setdefault(path[:-1], []).append(n)

    path: tuple = ()
    roots = children.get((), [])
    total_w, total_m = sum(n["wins"] for n in roots), sum(n["matches"] for n in roots)
    parent_wr = total_w / total_m if total_m else 0.5
    tiers: dict[int, int] = {}
    steps: list[Step] = []
    while path in children:
        sibs = children[path]
        top = max(n["matches"] for n in sibs)
        best = None
        for n in sibs:
            rel = n["matches"] / top
            if rel < cfg.min_rel_pop:
                continue
            wr = _smooth(n["wins"], n["matches"], parent_wr, cfg.prior_strength)
            score = wr + cfg.pop_weight * math.sqrt(rel)
            if best is None or score > best[0]:
                best = (score, n, wr)
        _, node, wr = best
        ability = node["abilities"][-1]
        tier = tiers.get(ability, -1) + 1
        if tier > MAX_TIER or (tier == 0 and len(tiers) >= MAX_UNLOCKS):
            break  # malformed data; keep what we have
        tiers[ability] = tier
        steps.append(Step(ability, tier, wr, node["matches"], node.get("avg_upgrade_time_s")))
        path = tuple(node["abilities"])
        parent_wr = node["wins"] / node["matches"]
    return complete(steps, tiers)


def complete(steps: list[Step], tiers: dict[int, int]) -> list[Step]:
    """Rare tails fall under the API's min_matches, so the walk can stop before every
    ability is maxed: finish the most invested abilities first (ties: unlocked earlier)."""
    first = {}
    for i, s in enumerate(steps):
        first.setdefault(s.ability_id, i)
    while True:
        open_ = [a for a, t in tiers.items() if t < MAX_TIER]
        if not open_:
            return steps
        a = min(open_, key=lambda a: (-tiers[a], first[a]))
        tiers[a] += 1
        steps.append(Step(a, tiers[a], None, 0, None))
