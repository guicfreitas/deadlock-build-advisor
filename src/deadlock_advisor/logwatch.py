"""Watches Deadlock's console.log (written when the game runs with -condebug).

Only reads a text file the game already writes; it never touches the game
process, so it is safe with respect to VAC.

Relevant lines (seen in real logs, build 6861):
  [SteamNetSockets] Received Steam datagram ticket for server steamid:... match_id=135235741
  Lobby 102161819384244930 for Match 135235741 created
  [Client] Map: "start"         -> the match map is loading
  [Client] Map: "dl_hideout"    -> back in the hideout (match over / left)
  Source2Shutdown               -> game closed
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

RE_MATCH_TICKET = re.compile(r"match_id=(\d+)")
RE_LOBBY = re.compile(r"Lobby \d+ for Match (\d+) created")
RE_MAP = re.compile(r'\[Client\] Map: "([^"]*)"')

HIDEOUT_MAPS = {"dl_hideout"}


@dataclass
class LogEvent:
    kind: str  # "match_found" | "match_map_loaded" | "match_ended" | "game_closed"
    match_id: int | None = None
    line: str = ""


def parse_line(line: str) -> LogEvent | None:
    m = RE_MATCH_TICKET.search(line) or RE_LOBBY.search(line)
    if m:
        return LogEvent("match_found", int(m.group(1)), line)
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
    return None


def current_match_from_lines(lines) -> int | None:
    """Replay a log to learn whether we are inside a match right now."""
    current: int | None = None
    for line in lines:
        ev = parse_line(line)
        if not ev:
            continue
        if ev.kind == "match_found":
            current = ev.match_id
        elif ev.kind in ("match_ended", "game_closed"):
            current = None
    return current


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
            mid = current_match_from_lines(text.splitlines())
            if mid:
                self._emit(LogEvent("match_found", mid, "(bootstrap)"))
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
