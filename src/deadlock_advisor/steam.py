"""Find Deadlock through the Steam client's own config files (read-only).

Reads the registry for the Steam install path, `steamapps/libraryfolders.vdf` for the
library folders, the app manifest for the install dir, `config/loginusers.vdf` for the
most recent account and `userdata/<id>/config/localconfig.vdf` for the launch options.
Nothing here touches the game's files.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DEADLOCK_APP_ID = "1422450"
STEAMID64_BASE = 76561197960265728
_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')


def parse_vdf(text: str) -> dict:
    """Minimal parser for Valve's text KeyValues format (what Steam's .vdf/.acf files use)."""
    root: dict = {}
    stack = [root]
    key = None
    for m in _TOKEN.finditer(text):
        s, brace = m.groups()
        if brace == "{":
            child: dict = {}
            stack[-1][key if key is not None else ""] = child
            stack.append(child)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        elif key is None:
            key = s.replace('\\\\', '\\').replace('\\"', '"')
        else:
            stack[-1][key] = s.replace('\\\\', '\\').replace('\\"', '"')
            key = None
    return root


def _get(d: dict, *path: str):
    """Case-insensitive nested lookup (Steam isn't consistent: "Software"/"valve"/"Steam")."""
    for p in path:
        if not isinstance(d, dict):
            return None
        d = next((v for k, v in d.items() if k.lower() == p.lower()), None)
    return d


def _read_vdf(path: Path) -> dict:
    try:
        return parse_vdf(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return {}


def steam_root() -> Path | None:
    candidates: list[Path] = []
    try:
        import winreg
        for hive, sub, name in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")):
            try:
                with winreg.OpenKey(hive, sub) as k:
                    candidates.append(Path(winreg.QueryValueEx(k, name)[0]))
            except OSError:
                pass
    except ImportError:  # not Windows
        pass
    candidates += [Path(r"C:\Program Files (x86)\Steam"), Path.home() / ".steam" / "steam"]
    return next((c for c in candidates if (c / "steamapps").is_dir()), None)


def library_folders(root: Path) -> list[Path]:
    libs = [root]
    data = _get(_read_vdf(root / "steamapps" / "libraryfolders.vdf"), "libraryfolders") or {}
    for entry in data.values():
        p = entry.get("path") if isinstance(entry, dict) else entry  # old format: "1" "D:\\Lib"
        if isinstance(p, str) and Path(p) not in libs:
            libs.append(Path(p))
    return libs


def find_game_dir(root: Path | None = None) -> Path | None:
    root = root or steam_root()
    if not root:
        return None
    for lib in library_folders(root):
        manifest = lib / "steamapps" / f"appmanifest_{DEADLOCK_APP_ID}.acf"
        installdir = _get(_read_vdf(manifest), "AppState", "installdir") if manifest.exists() else None
        for name in filter(None, (installdir, "Deadlock")):
            game = lib / "steamapps" / "common" / name
            if (game / "game" / "citadel").is_dir():
                return game
    return None


def most_recent_account(root: Path | None = None) -> int | None:
    """SteamID3 of the account that last logged in to this Steam client."""
    root = root or steam_root()
    if not root:
        return None
    users = _get(_read_vdf(root / "config" / "loginusers.vdf"), "users") or {}
    best = None
    for sid64, u in users.items():
        if not (isinstance(u, dict) and sid64.isdigit()):
            continue
        ts = int(u.get("Timestamp") or 0) + (10**12 if u.get("MostRecent") == "1" else 0)
        if best is None or ts > best[0]:
            best = (ts, int(sid64) - STEAMID64_BASE)
    return best[1] if best else None


def launch_options(account_id: int, root: Path | None = None) -> str | None:
    """Deadlock's launch options as set in Steam, or None if unknown."""
    root = root or steam_root()
    if not root:
        return None
    cfg = _read_vdf(root / "userdata" / str(account_id) / "config" / "localconfig.vdf")
    app = _get(cfg, "UserLocalConfigStore", "Software", "Valve", "Steam", "apps", DEADLOCK_APP_ID)
    if not isinstance(app, dict):
        return None
    return app.get("LaunchOptions", "")


@dataclass
class SetupCheck:
    """What the first-run screen shows. Every field is user-facing state, not an error."""
    steam_found: bool
    game_dir: str | None
    account_id: int | None
    launch_options: str | None   # None = could not read them
    condebug: bool | None        # None = unknown
    console_log: bool
    # when the game last wrote console.log. Steam can be slow to save launch options to
    # localconfig.vdf, so the first-run screen also accepts "the log was written after the
    # player said they added -condebug" as proof.
    console_log_mtime: float | None = None

    @property
    def ok(self) -> bool:
        return bool(self.game_dir and self.account_id and self.console_log and self.condebug is not False)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "steam_found": self.steam_found, "game_dir": self.game_dir,
                "account_id": self.account_id, "launch_options": self.launch_options,
                "condebug": self.condebug, "console_log": self.console_log,
                "console_log_mtime": self.console_log_mtime}


def check_setup(game_dir: Path | None, account_id: int | None, root: Path | None = None) -> SetupCheck:
    root = root or steam_root()
    opts = launch_options(account_id, root) if (root and account_id) else None
    condebug = None if opts is None else bool(re.search(r"(^|\s)-condebug(\s|$)", opts))
    path = Path(game_dir) / "game" / "citadel" / "console.log" if game_dir else None
    try:
        mtime = path.stat().st_mtime if path else None
    except OSError:
        mtime = None
    return SetupCheck(root is not None, str(game_dir) if game_dir else None, account_id, opts, condebug,
                      mtime is not None, mtime)
