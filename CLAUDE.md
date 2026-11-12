# Deadlock Build Advisor — notes for Claude

- Python 3.10+, **stdlib only** (urllib, http.server, tkinter). Don't add dependencies without asking.
- Run: `$env:PYTHONPATH="src"; python -m deadlock_advisor` · Tests: `python -m pytest -q -p no:anyio`.
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
- Street Brawl (4v4, `game_mode` 4, every lane reported as 0) is **out of scope**: items are drafted,
  not bought. Only the standard map is supported (casual/unranked and competitive/ranked).

## What the game itself exposes (tested in a live match, 2026-11-12)
- No Game State Integration: no GSI code in any client or engine DLL.
- The combat log (`citadel_combat_log_*`) is off in matchmaking: `citadel_combat_log_enabled_in_lobbies`
  is a dev-only cvar.
- The `status` console command lists player **names**, the map and the game state, but not heroes or SteamIDs.
- Hero resource paths in console.log are noise: the UI and skins load heroes that are not in the match.
- So the live broadcast through deadlock-api is the only VAC-safe source for the enemy heroes.
- Item stats are confounded by the matchup itself. `engine.score_items` subtracts the context offset;
  keep that when changing the scoring.
