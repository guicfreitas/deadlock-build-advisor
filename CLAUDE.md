# Deadlock Build Advisor — notes for Claude

- Python 3.10+, **stdlib only** (urllib, http.server, tkinter). Don't add dependencies without asking.
- Run: `$env:PYTHONPATH="src"; python -m deadlock_advisor` · Tests: `python -m pytest -q -p no:anyio`.
- Package: `packaging\build.ps1` (PyInstaller in `.venv-build` + Inno Setup 6; both build-only, approved
  by the user). The windowed .exe has `sys.stdout is None`: `__main__` redirects it to
  `%LOCALAPPDATA%\deadlock-advisor\advisor.log`. Settings live in `%APPDATA%\deadlock-advisor`.
- The web server binds with SO_EXCLUSIVEADDRUSE: http.server's SO_REUSEADDR lets two copies share
  the port on Windows. A second launch opens the page of the running one and exits.
- UI text and README are in Brazilian Portuguese; code/comments in English.
- **Never** inject into the game process, read its memory, or modify game files: VAC risk. Only read
  `game/citadel/console.log` (needs `-condebug`) and call https://api.deadlock-api.com.
- Game install: `D:\SteamLibrary\steamapps\common\Deadlock` (game data in `game\citadel`).

## deadlock-api gotchas (verified)
- OpenAPI: https://api.deadlock-api.com/openapi.json; analytics share a 200 req/min IP limit.
- Live roster: `GET /v1/matches/demo/live/query?match_id=..&query=SQL` (SSE). DataFusion SQL:
  the table name goes **unquoted** (`CCitadelPlayerController`) and the columns go **double-quoted**
  (`"m_PlayerDataGlobal__m_nHeroID"`). Teams come back as 2/3 (we map them to 0/1). Lanes are 1/4/6.
  Spectating is limited to ~6/h without an API key; a match spectated within the last hour is cached.
- `k_eNotInGame` means the match has not started or is already over: retry with backoff.
- Heavy analytics queries over the default 30-day window can return HTTP 504, and Cloudflare then
  serves that cached 504 for the same URL. `api.analytics` retries with `min_unix_timestamp` = 14
  days ago, rounded to the day so the URL stays cacheable. The ability-order tree always uses 14 days.
- Ability order: `/v1/analytics/ability-order-tree` nodes are prefixes, one entry per upgrade
  (unlocks included). Deeper prefixes win more (survivorship: winners level faster), so
  `abilities.pick_order` only compares siblings. Don't show the full path's win rate in the UI.
- Street Brawl (4v4, `game_mode` 4, every lane reported as 0) is **out of scope**: items are drafted,
  not bought. Only the standard map is supported (casual/unranked and competitive/ranked).

## Self-update (`updater.py`)
- Follows `https://api.github.com/repos/<update_repo>/releases/latest`. The asset must be named
  `DeadlockBuildAdvisor-Setup-<ver>.exe` and have a SHA-256 (GitHub's asset `digest` or the
  `.sha256` file from `build.ps1`); without one it refuses to install.
- Runs the installer with `/SILENT ... /CURRENTUSER|/ALLUSERS` (keeps the original install scope)
  and quits; the `skipifnotsilent` [Run] entry in installer.iss reopens the app. Never installs
  while `Advisor.in_match`. From source it only notifies.
- The repo was private on 2026-11-12 (the API returns 404 without login), so updates need public releases.

## What the game itself exposes (tested in a live match, 2026-11-12)
- No Game State Integration: no GSI code in any client or engine DLL.
- The combat log (`citadel_combat_log_*`) is off in matchmaking: `citadel_combat_log_enabled_in_lobbies`
  is a dev-only cvar.
- The `status` console command lists player **names**, the map and the game state, but not heroes or SteamIDs.
- Hero resource paths in console.log are noise: the UI and skins load heroes that are not in the match.
- Your own hero is not known before the match either: you queue with a priority **list**
  (`citadel_hero_roster_high_priority` in `user_convars`) and matchmaking picks one from it.
- So the live broadcast through deadlock-api is the only VAC-safe source for the heroes.
- Measured delay in a real casual match: about 85 s from "match found" to build ready, which
  landed about 2 s after the game clock started at 0:00. The wait is the Valve broadcast relay.
- Lanes can be swapped in the ~30 s prep window. `m_bLaneSwapLocked` says when that is over; on a
  real match (2026-11-12) the relay was ready 58 s after spectating with all 12 already locked,
  so `_watch_lanes` only runs while some lane is unlocked (max 5 min).
- A few minutes in, `m_nAssignedLane` drops back to 0 for everyone (lane phase over?). It is not
  a swap: `live._merge` keeps the last real lane, otherwise the lane build would be wiped.
- Item stats are confounded by the matchup itself. `engine.score_items` subtracts the context offset;
  keep that when changing the scoring.

## In-game build share codes (verified in game, 2026-11-12)
- Hero Builds editor has "Copiar para a área de transferência" / "Colar guia": the text is
  base64(zstd(protobuf CMsgHeroBuild)). `gamebuild.py` writes it with uncompressed zstd blocks
  (no zstd in the 3.12 stdlib) and the game accepts that. Field map is in its docstring.
- "Colar guia" silently drops a build without header fields 1, 3, 4, 9 and 13 (it pastes an
  empty category). Categories need width/height or the box hides the items. There is no box
  position: boxes flow left to right, so full-row width (900) stacks them vertically.
- Names like `#Citadel_HeroBuilds_MidGame` are localized by the game. Ability order is a list of
  currency changes: type 2 unlocks an ability, type 1 buys an upgrade at 1/2/5 points.
- To decode a code the game copied, Node 22+ has `zlib.zstdDecompressSync`.
- Never hand-retype a share code in chat: one typo makes the game reject it. Put it on the
  clipboard from the program (`clipboard.set_text`).

## Enemy items mid-match (verified on a live match, 2026-11-12)
- `CCitadelPlayerController."m_PlayerDataGlobal__m_vecUpgrades"` is List(Binary): 8-byte hex
  blobs, item id = little-endian uint32 of the first 4 bytes (`live.decode_upgrades`).
- The live query streams every row of every tick (~13 MB/min with that column) and ignores
  filters on `tick` (`tick % 320 = 0` returns nothing). So `live.snapshot_items` reads one set
  of 12 players and disconnects; with the match already spectated it takes 2-5 s.
- Python's default urllib User-Agent gets HTTP 403: always go through `DeadlockApi`.
- `counters.py` maps enemy items (by class_name) to threats and answers; the stats API can't
  condition on enemy items, only heroes. The answer is picked by `rec["item_lift"]`.
