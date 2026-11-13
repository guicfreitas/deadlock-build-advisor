"""Hand-written lane counters, on top of the statistics.

The stats alone favor what everybody buys, and miss answers that experienced players know
(community feedback on r/DeadlockTheGame, 2026-11). Sources for the gun rule: the
thebackdash "complete counter item guide" (Rusted Barrel, Suppressor, Disarming Hex,
Hunter's Aura and Juggernaut counter gun heroes), Esports Insider (fire rate reduction
against Wraith, Vyper, Vindicta) and a McGinnis guide (Suppressor early in lane against
Haze or Wraith).

Heroes and items are keyed by class_name, which is stable across patches and languages.
"""
from __future__ import annotations

GUN_HEROES = frozenset({"hero_haze", "hero_wraith", "hero_vyper", "hero_vindicta"})
# Suppressor first (1600 souls); Rusted Barrel (800 souls, class name upgrade_withering_whip)
# when two gun heroes share the lane, or when Suppressor has no usable stats.
ANTI_GUN_LANE = ("upgrade_suppressor", "upgrade_withering_whip")
