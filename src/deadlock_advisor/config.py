from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import steam

CONFIG_FILE = Path(os.environ.get("DEADLOCK_ADVISOR_CONFIG", "config.json"))


@dataclass
class Config:
    game_dir: str = ""                 # empty = find it through the Steam libraries
    account_id: int | None = None      # SteamID3; auto-detected from citadel/account_<id>.stats
    api_key: str | None = None         # optional deadlock-api key (higher live-spectate limits)
    port: int = 8787
    overlay: bool = True
    overlay_alpha: float = 0.88
    cache_dir: str = str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "deadlock-advisor" / "cache")
    engine: dict = field(default_factory=dict)  # overrides for EngineConfig (see engine.py)

    @property
    def citadel_dir(self) -> Path:
        return Path(self.game_dir) / "game" / "citadel"

    @property
    def console_log(self) -> Path:
        return self.citadel_dir / "console.log"

    def detect_game_dir(self) -> str:
        if self.game_dir and (Path(self.game_dir) / "game" / "citadel").is_dir():
            return self.game_dir
        found = steam.find_game_dir()
        if found:
            self.game_dir = str(found)
        return self.game_dir

    def detect_account_id(self) -> int | None:
        if self.account_id:
            return self.account_id
        # the account last logged in to Steam is the one playing; the .stats files can
        # belong to several accounts that used this PC
        recent = steam.most_recent_account()
        if recent:
            self.account_id = recent
            return recent
        try:
            for p in self.citadel_dir.glob("account_*.stats"):
                m = re.match(r"account_(\d+)\.stats$", p.name)
                if m:
                    self.account_id = int(m.group(1))
                    return self.account_id
        except OSError:
            pass
        return None


def load_config(path: Path = CONFIG_FILE) -> Config:
    cfg = Config()
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        for k, v in data.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
    cfg.api_key = cfg.api_key or os.environ.get("DEADLOCK_API_KEY")
    cfg.detect_game_dir()
    cfg.detect_account_id()
    return cfg
