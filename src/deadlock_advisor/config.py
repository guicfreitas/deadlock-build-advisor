from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import steam
from .i18n import LANGUAGES, t

def data_dir() -> Path:
    """Per-user, writable folder (an installed app can't write next to its .exe)."""
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "deadlock-advisor"


def config_path() -> Path:
    """$DEADLOCK_ADVISOR_CONFIG > ./config.json (running from source) > %APPDATA%."""
    if os.environ.get("DEADLOCK_ADVISOR_CONFIG"):
        return Path(os.environ["DEADLOCK_ADVISOR_CONFIG"])
    local = Path("config.json")
    return local if local.exists() else data_dir() / "config.json"


CONFIG_FILE = config_path()

# What the settings screen may change: key -> (validator, applied without restart?)
RANKS_MAX_BADGE = 116  # badge = tier * 10 + subtier; tier 11 (Eternus) is the top


def _opt_int(lo: int, hi: int):
    def check(v):
        if v in (None, ""):
            return None
        v = int(v)
        if not lo <= v <= hi:
            raise ValueError(t("err.range", lo=lo, hi=hi))
        return v
    return check


def _num(lo: float, hi: float, kind=int):
    def check(v):
        v = kind(v)
        if not lo <= v <= hi:
            raise ValueError(t("err.range", lo=lo, hi=hi))
        return v
    return check


def _game_dir(v):
    v = (v or "").strip().strip('"')
    if v and not (Path(v) / "game" / "citadel").is_dir():
        raise ValueError(t("err.not_game_dir"))
    return v


def _language(v):
    v = (v or "").strip()
    if v and v not in LANGUAGES:
        raise ValueError(t("err.invalid"))
    return v


def _opt_str(v):
    v = (v or "").strip()
    return v or None


EDITABLE = {
    "game_dir": (_game_dir, False),
    "account_id": (_opt_int(1, 2**32 - 1), True),
    "api_key": (_opt_str, True),
    "port": (_num(1024, 65535), False),
    "overlay": (bool, False),
    "overlay_alpha": (_num(0.3, 1.0, float), False),
    "auto_update": (bool, True),
    "language": (_language, False),
    "engine.lane_window_s": (_num(300, 900), True),
    "engine.lane_budget": (_num(1000, 12000), True),
    "engine.filters.min_average_badge": (_opt_int(0, RANKS_MAX_BADGE), True),
}


@dataclass
class Config:
    game_dir: str = ""                 # empty = find it through the Steam libraries
    account_id: int | None = None      # SteamID3; auto-detected from citadel/account_<id>.stats
    api_key: str | None = None         # optional deadlock-api key (higher live-spectate limits)
    port: int = 8787
    overlay: bool = True
    overlay_alpha: float = 0.88
    auto_update: bool = True           # install new releases by itself (out of a match)
    language: str = ""                 # UI language code ("" = follow the system language)
    update_repo: str = "guicfreitas/deadlock-build-advisor"  # GitHub repo whose releases we follow
    cache_dir: str = str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "deadlock-advisor" / "cache")
    engine: dict = field(default_factory=dict)  # overrides for EngineConfig (see engine.py)
    path: Path = field(default_factory=config_path, repr=False)   # where settings are saved
    user: dict = field(default_factory=dict, repr=False)          # only what the user set

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


def _get_path(d: dict, dotted: str):
    for part in dotted.split("."):
        if not isinstance(d, dict) or part not in d:
            return None
        d = d[part]
    return d


def _set_path(d: dict, dotted: str, value) -> None:
    *parents, last = dotted.split(".")
    for part in parents:
        d = d.setdefault(part, {})
    if value is None:
        d.pop(last, None)
    else:
        d[last] = value


def load_config(path: Path | None = None) -> Config:
    path = path or CONFIG_FILE
    cfg = Config()
    cfg.path = path
    cfg.user = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:  # a broken file must not stop the app; settings screen rewrites it
            data = {}
        cfg.user = data if isinstance(data, dict) else {}
        for k, v in cfg.user.items():
            if hasattr(cfg, k) and k not in ("path", "user"):
                setattr(cfg, k, v)
    cfg.api_key = cfg.api_key or os.environ.get("DEADLOCK_API_KEY")
    cfg.detect_game_dir()
    cfg.detect_account_id()
    return cfg


def settings_view(cfg: Config) -> dict:
    """Current values for the settings screen: what the user set, and what is in effect."""
    effective = {"game_dir": cfg.game_dir, "account_id": cfg.account_id, "api_key": cfg.api_key,
                 "port": cfg.port, "overlay": cfg.overlay, "overlay_alpha": cfg.overlay_alpha,
                 "auto_update": cfg.auto_update, "language": cfg.language, "engine": cfg.engine}
    return {"path": str(cfg.path),
            "user": {k: _get_path(cfg.user, k) for k in EDITABLE},
            "effective": {k: _get_path(effective, k) for k in EDITABLE}}


def update_settings(cfg: Config, changes: dict) -> dict:
    """Validate and save user settings. Empty values go back to auto-detection/defaults.

    Returns {"saved": [...], "restart": [...], "errors": {key: message}}; nothing is saved
    if any value is invalid.
    """
    errors, clean = {}, {}
    for key, value in changes.items():
        if key not in EDITABLE:
            errors[key] = t("err.unknown_field")
            continue
        check, _ = EDITABLE[key]
        try:
            clean[key] = check(value) if value is not None else None
        except (TypeError, ValueError) as e:
            errors[key] = str(e) or t("err.invalid")
    if errors:
        return {"saved": [], "restart": [], "errors": errors}

    user = json.loads(json.dumps(cfg.user))  # deep copy
    for key, value in clean.items():
        default = _get_path(DEFAULTS, key)
        _set_path(user, key, None if value == default else value)
    cfg.path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cfg.path.with_suffix(".tmp")
    tmp.write_text(json.dumps(user, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(cfg.path)
    cfg.user = user

    # apply what works live; the rest waits for a restart
    restart = []
    for key, value in clean.items():
        top = key.split(".")[0]
        if not EDITABLE[key][1]:
            restart.append(key)
            continue
        if top == "engine":
            cfg.engine = json.loads(json.dumps(user.get("engine", {})))
        elif top == "api_key":
            cfg.api_key = value or os.environ.get("DEADLOCK_API_KEY")
        elif top == "auto_update":
            cfg.auto_update = value is not False
        elif top == "account_id":
            cfg.account_id = value
            cfg.detect_account_id()
    return {"saved": list(clean), "restart": restart, "errors": {}}


DEFAULTS = {"game_dir": "", "account_id": None, "api_key": None, "port": 8787, "overlay": True,
            "overlay_alpha": 0.88, "auto_update": True, "language": "", "engine": {"lane_window_s": 600, "lane_budget": 5600}}
