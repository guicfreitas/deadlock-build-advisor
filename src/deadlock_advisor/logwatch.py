"""Watches Deadlock's console.log (written when the game runs with -condebug).

Only reads a text file the game already writes; it never touches the game
process, so it is safe with respect to VAC.

Relevant lines (seen in real logs, build 6861):
  [SteamNetSockets] Received Steam datagram ticket for server steamid:... match_id=135235741
  Lobby 102161819384244930 for Match 135235741 created
  [Client] Map: "start"         -> the match map is loading
  [Client] Map: "dl_hideout"    -> back in the hideout (match over / left)
  Source2Shutdown               -> game closed
  OnGameStateChanged: GameInProgress (7)  -> the match clock starts at 0:00 (the hideout logs the
                                   same line, so it only counts after "match found")
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

RE_MATCH_TICKET = re.compile(r"match_id=(\d+)")
RE_LOBBY = re.compile(r"Lobby \d+ for Match (\d+) created")
RE_LOBBY_END = re.compile(r"Lobby \d+ for Match \d+ destroyed")
RE_MAP = re.compile(r'\[Client\] Map: "([^"]*)"')
RE_GAME_START = re.compile(r"OnGameStateChanged: GameInProgress \(7\)")
RE_STAMP = re.compile(r"^(\d\d)/(\d\d) (\d\d):(\d\d):(\d\d) ")

HIDEOUT_MAPS = {"dl_hideout"}


@dataclass
class LogEvent:
    kind: str  # "match_found" | "match_map_loaded" | "game_started" | "match_ended" | "game_closed"
    match_id: int | None = None
    line: str = ""
    ts: float | None = None   # when the game wrote the line (epoch seconds), if it said so


def line_time(line: str, now: datetime | None = None) -> float | None:
    """Epoch seconds of a console.log line ("MM/DD HH:MM:SS ..." in local time, no year)."""
    m = RE_STAMP.match(line)
    if not m:
        return None
    now = now or datetime.now()
    mo, d, h, mi, sec = (int(x) for x in m.groups())
    try:
        when = datetime(now.year, mo, d, h, mi, sec)
    except ValueError:
        return None
    if when > now + timedelta(days=1):  # a log from late December read in January
        when = when.replace(year=now.year - 1)
    return when.timestamp()


def parse_line(line: str) -> LogEvent | None:
    m = RE_MATCH_TICKET.search(line) or RE_LOBBY.search(line)
    if m:
        return LogEvent("match_found", int(m.group(1)), line)
    if RE_LOBBY_END.search(line):
        return LogEvent("match_ended", None, line)
    m = RE_MAP.search(line)
    if m:
        name = m.group(1)
        if name in HIDEOUT_MAPS:
            return LogEvent("match_ended", None, line)
        if name and name != "<empty>":
            return LogEvent("match_map_loaded", None, line)
        return None
    if "Source2Shutdown" in line:
        return LogEvent("game_closed", None, line)
    if RE_GAME_START.search(line):
        return LogEvent("game_started", None, line, line_time(line))
    return None


def replay(lines) -> tuple[int | None, float | None]:
    """Replay a log: (match we are in right now, when its clock started)."""
    current: int | None = None
    started: float | None = None
    for line in lines:
        ev = parse_line(line)
        if not ev:
            continue
        if ev.kind == "match_found":
            if ev.match_id != current:
                started = None
            current = ev.match_id
        elif ev.kind in ("match_ended", "game_closed"):
            current, started = None, None
        elif ev.kind == "game_started" and current:
            started = ev.ts
    return current, started


def current_match_from_lines(lines) -> int | None:
    """Replay a log to learn whether we are inside a match right now."""
    return replay(lines)[0]


class ConsoleLogWatcher(threading.Thread):
    """Tails console.log and calls `on_event` for each relevant event.

    Handles the file being recreated when the game restarts.
    """

    def __init__(self, path: Path, on_event: Callable[[LogEvent], None], poll_s: float = 0.5):
        super().__init__(daemon=True, name="console-log-watcher")
        self.path = Path(path)
        self.on_event = on_event
        self.poll_s = poll_s
        self._stop = threading.Event()
        self.last_match_id: int | None = None

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        pos = 0
        # Bootstrap: are we already in a match?
        if self.path.exists():
            text = self.path.read_text(encoding="utf-8", errors="replace")
            pos = self.path.stat().st_size
            mid, started = replay(text.splitlines())
            if mid:
                self._emit(LogEvent("match_found", mid, "(bootstrap)"))
                if started:  # the app was opened mid-match: the clock is already running
                    self._emit(LogEvent("game_started", None, "(bootstrap)", started))
        buf = b""
        while not self._stop.is_set():
            try:
                size = self.path.stat().st_size
            except FileNotFoundError:
                time.sleep(self.poll_s * 4)
                continue
            if size < pos:  # truncated / recreated on game restart
                pos, buf = 0, b""
            if size > pos:
                with self.path.open("rb") as f:
                    f.seek(pos)
                    chunk = f.read(size - pos)
                pos = size
                buf += chunk
                *lines, buf = buf.split(b"\n")
                for raw in lines:
                    ev = parse_line(raw.decode("utf-8", errors="replace"))
                    if ev:
                        self._emit(ev)
            time.sleep(self.poll_s)

    def _emit(self, ev: LogEvent) -> None:
        if ev.kind == "match_found":
            if ev.match_id == self.last_match_id:
                return  # ticket + lobby lines both announce the same match
            self.last_match_id = ev.match_id
        elif ev.kind in ("match_ended", "game_closed"):
            self.last_match_id = None
        self.on_event(ev)
