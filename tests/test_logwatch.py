from deadlock_advisor.logwatch import ConsoleLogWatcher, current_match_from_lines, parse_line

# Lines copied from a real console.log (build 6861)
TICKET = ("11/10 22:04:29 [SteamNetSockets] Received Steam datagram ticket for server "
          "steamid:90297244937270296 vport -1. match_id=135235741")
LOBBY = "11/10 22:04:29 Lobby 102161819384244930 for Match 135235741 created"
MAP_START = '11/10 22:04:31 [Client] Map: "start"'
MAP_HIDEOUT = '11/10 22:28:24 [Client] Map: "dl_hideout"'


def test_parse_lines():
    assert parse_line(TICKET).kind == "match_found"
    assert parse_line(TICKET).match_id == 135235741
    assert parse_line(LOBBY).match_id == 135235741
    assert parse_line(MAP_START).kind == "match_map_loaded"
    assert parse_line(MAP_HIDEOUT).kind == "match_ended"
    assert parse_line('[Client] Map: "<empty>"') is None
    assert parse_line("11/10 23:05:29 Source2Shutdown").kind == "game_closed"
    assert parse_line("random noise") is None


def test_current_match_replay():
    assert current_match_from_lines([MAP_HIDEOUT, TICKET, MAP_START]) == 135235741
    assert current_match_from_lines([TICKET, MAP_START, MAP_HIDEOUT]) is None


def test_watcher_tails_and_dedupes(tmp_path):
    log = tmp_path / "console.log"
    log.write_text(MAP_HIDEOUT + "\n", encoding="utf-8")
    events = []
    w = ConsoleLogWatcher(log, events.append, poll_s=0.05)
    w.start()
    import time
    time.sleep(0.2)
    with log.open("a", encoding="utf-8") as f:
        f.write(TICKET + "\n" + LOBBY + "\n" + MAP_START + "\n")
    time.sleep(0.3)
    with log.open("a", encoding="utf-8") as f:
        f.write(MAP_HIDEOUT + "\n")
    time.sleep(0.3)
    w.stop()
    kinds = [e.kind for e in events]
    assert kinds == ["match_found", "match_map_loaded", "match_ended"]
    assert events[0].match_id == 135235741
