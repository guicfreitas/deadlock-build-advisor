from datetime import datetime

from deadlock_advisor import sound, timers
from deadlock_advisor.logwatch import line_time, parse_line, replay

TICKET = "11/16 16:39:07 [SteamNetSockets] Received Steam datagram ticket for server steamid:1 vport -1. match_id=138733040"
HIDEOUT_START = "11/16 16:36:30 OnGameStateChanged: GameInProgress (7)"   # the hideout logs it too
MATCH_START = "11/16 16:40:09 OnGameStateChanged: GameInProgress (7)"      # real line, 2026-11-16


def test_game_start_parsed_with_time():
    ev = parse_line(MATCH_START)
    assert ev.kind == "game_started"
    assert datetime.fromtimestamp(ev.ts).strftime("%m/%d %H:%M:%S") == "11/16 16:40:09"


def test_replay_ignores_the_hideout_clock():
    assert replay([HIDEOUT_START])[1] is None          # no match yet
    mid, started = replay([HIDEOUT_START, TICKET, MATCH_START])
    assert mid == 138733040 and started == line_time(MATCH_START)
    assert replay([TICKET])[1] is None                  # match found, clock not started
    assert replay([TICKET, MATCH_START, '[Client] Map: "dl_hideout"']) == (None, None)


def test_line_time_year_rollover():
    assert datetime.fromtimestamp(line_time("12/31 23:59:00 x", datetime(2027, 1, 1, 0, 5))).year == 2026
    assert line_time("garbage") is None


def test_schedule_first_spawns_and_repeats():
    first = {k: at for at, k in reversed(timers.schedule())}
    assert first == {"small_camps": 120, "crates": 180, "medium_camps": 300, "large_camps": 480, "vault": 480}
    crates = [at for at, k in timers.schedule() if k == "crates"]
    assert crates[:3] == [180, 360, 540]
    assert [k for _, k in timers.schedule() if k == "small_camps"] == ["small_camps"]  # once only


def test_upcoming_and_due_window():
    assert timers.upcoming(0, 2) == [(120, "small_camps"), (180, "crates")]
    assert timers.upcoming(120, 1) == [(180, "crates")]            # already spawned: gone
    assert timers.due(100) == []
    assert timers.due(105) == [(120, "small_camps")]               # LEAD_S = 15 before
    assert timers.due(120) == []                                   # spawned: no more warning


def test_sound_never_raises(monkeypatch):
    sound.play("nonexistent")
    monkeypatch.setattr(sound.sys, "platform", "linux")
    sound.play("ready")
