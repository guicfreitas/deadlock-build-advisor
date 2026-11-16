"""Respawn timers on the match clock (0:00 = the log's GameInProgress line).

Numbers from the community wiki (https://deadlock.wiki/Timers, checked 2026-11-16; the page
itself says it may be out of date after patches, so they live here in one table):
  small ("easy") camps  first spawn 2:00, respawn 1:25 after cleared
  crates / breakables   first spawn 3:00, respawn 3:00 after broken
  medium camps          first spawn 5:00, respawn 4:50 after cleared
  large ("hard") camps  first spawn 8:00, respawn 5:35 after cleared
  vault (Sinner's Sacrifice) first spawn 8:00, respawn 5:00 after cleared

Only the first spawn is exact. A respawn counts from the moment the player clears the camp,
which we cannot see, so the repeats assume it was cleared right when it spawned: a guide,
never a promise. Small camps (every 1:25) would be pure noise, so they only warn once.
"""
from __future__ import annotations

LEAD_S = 15          # warn this many seconds before the spawn (time to get there)
MAX_CLOCK_S = 3600   # nothing past an hour is worth scheduling

# key (also the locale key "timer.<key>"), first spawn (s), repeat every (s) or None = once
EVENTS: tuple[tuple[str, int, int | None], ...] = (
    ("small_camps", 120, None),
    ("crates", 180, 180),
    ("medium_camps", 300, 290),
    ("large_camps", 480, 335),
    ("vault", 480, 300),
)


def schedule(events=EVENTS, until_s: int = MAX_CLOCK_S) -> list[tuple[int, str]]:
    """Every (clock second, key), sorted."""
    out: list[tuple[int, str]] = []
    for key, first, every in events:
        at = first
        while at <= until_s:
            out.append((at, key))
            if not every:
                break
            at += every
    return sorted(out)


def upcoming(elapsed_s: float, count: int = 4, events=EVENTS) -> list[tuple[int, str]]:
    """The next `count` spawns that have not happened yet."""
    return [e for e in schedule(events) if e[0] > elapsed_s][:count]


def due(elapsed_s: float, events=EVENTS) -> list[tuple[int, str]]:
    """Spawns inside the warning window right now (LEAD_S before until the spawn)."""
    return [e for e in schedule(events) if e[0] - LEAD_S <= elapsed_s < e[0]]
