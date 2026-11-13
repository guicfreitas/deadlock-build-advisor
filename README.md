<div align="center">

**English · [Português (Brasil)](README.pt-BR.md)**

# Deadlock Build Advisor

**Counter builds for Deadlock, put together on the fly from the heroes in your match.**

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)
![VAC](https://img.shields.io/badge/VAC-safe-success)

</div>

When a match starts, the app finds out who you're up against and builds three recommendations:

| | What it is | Against whom |
|---|---|---|
| 🛡️ **Lane build** | items for the first ~10 minutes, within a realistic souls budget | the duo in **your lane** |
| ⚔️ **Full build** | mid and late game items | the **whole enemy team** |
| 🎯 **Counters per opponent** | the items with the biggest edge against each enemy, and your win rate in that matchup | each enemy |

And during the match:

- 📋 **Copy to the game**: one click copies the build in Deadlock's own build-sharing format. In the game, open *Browse builds*, create a build and click **Paste build**: categories, items and notes come in ready, and Quick Buy follows the build.
- 🔄 **Swap to counter**: every minute the app reads what the enemies bought and, when a threat shows up (lots of healing, weapon damage, spirit damage, crowd control, resistances), suggests "buy X instead of Y" for the build you pasted, and tells you who bought what.

Recommendations show up in an **always-on-top overlay** and on a **local web page** (`http://localhost:8787`) that you can open on a second monitor or your phone.

> [!NOTE]
> Works in **casual** and **ranked** (standard 6v6 map). **Street Brawl** (4v4) is not supported: items are drafted there, not bought. The app detects it and just tells you.

## Languages

English, Português (Brasil), Español, Русский and 简体中文. The app follows your Windows language (change it in Settings; applies after a restart). Hero and item names follow the same language. To add one, copy `src/deadlock_advisor/locales/en.json`, translate the values, and register the code in `LANGUAGES` in `i18n.py`.

## Is it safe? (VAC)

**Yes.** The app **injects nothing into the game, never reads the process memory and never modifies game files**. It only:

- reads `console.log`, a text file the game writes itself when launched with `-condebug`;
- queries the community API [deadlock-api.com](https://deadlock-api.com);
- draws its own window on top of the game.

Why not read the heroes straight from the game? Because Deadlock doesn't expose that safely: there's no Game State Integration, the combat log is off in matchmaking and the `status` command only shows names. Valve's live broadcast, reached through deadlock-api, is the one source that never touches the game.

## Quick start

1. **Download and run the installer** `DeadlockBuildAdvisor-Setup-x.y.z.exe` from the *Releases* page. No Python needed, and no admin password.
2. **Turn on the game log.** In Steam: Deadlock → Properties → Launch Options → add `-condebug`.
3. **Use borderless windowed.** In the game's video settings pick *Borderless*; the overlay can't draw over exclusive fullscreen.
4. **Open the app** from the *Deadlock Build Advisor* shortcut. It finds the game folder and your account through your Steam libraries. The first time, the page walks you through three steps that tick themselves off.
5. **Join a match.** The status changes to "Match found" and the build shows up shortly after (about 1–2 minutes: that's Valve's broadcast delay).

> [!TIP]
> If detection fails (say, Steam in an unusual place), set the game folder in **Settings**. In Steam: Deadlock → Properties → Installed Files → **Browse**.

## Settings

Everything is optional and lives in **Settings** on the app's page: game folder, Steam account, language, the rank of the matches used for the stats, lane length and souls, overlay on/off and transparency, automatic updates, and an optional data-service key (without one, about 6 matches per hour can be followed).

## Common problems

| Symptom | Likely cause |
|---|---|
| "The game log is not turned on" / "doesn't exist yet" | `-condebug` is missing from the launch options, or the game folder is wrong. |
| Stuck on "Waiting for a match…" | The game was opened without `-condebug`. Close Deadlock, add it and open it again. |
| "Couldn't find your Steam account" | Enter your Steam account number in Settings. |
| Error reading players after many matches in a row | Without a key, about 6 matches per hour can be followed. Wait a bit, or use manual mode on the page. |
| Overlay doesn't show over the game | The game is in exclusive fullscreen. Switch to *Borderless*. |

## Feedback and support

Found a bug or have an idea? Use **Feedback & help** at the bottom of the app's page: it opens a GitHub issue with your app version already filled in (no personal data). You can also [open an issue](../../issues/new) directly.

The app is free, has no ads and nothing is locked. If it helps you, you can chip in:

- ☕ [Buy Me a Coffee](https://buymeacoffee.com/guicfreitas)
- 💬 Discord: `_guicf`

## Built with AI assistance

This project was built with help from Claude (an AI coding assistant); the author is a developer working outside their usual platform. The recommendations themselves do **not** come from an AI model: they are plain, deterministic statistics over recent match data, plus a few hand-written lane counter rules (see `src/deadlock_advisor/lane_rules.py`, with sources in the file). Feedback from players who know the game better is what makes the rules better.

## Development

See [README.pt-BR.md](README.pt-BR.md) for how it works internally (in Portuguese) and `CLAUDE.md` for the project notes.

```powershell
pip install pytest
python -m pytest -q -p no:anyio
$env:PYTHONPATH="src"; python -m deadlock_advisor
```

## License

All rights reserved. The code is here for reference only: you may read it and use the app through the official installers, for personal, non-commercial use. Copying, modifying, redistributing or selling it, in whole or in part, is not allowed without written permission. See [LICENSE](LICENSE).

## Credits

Match data and stats come from [deadlock-api.com](https://deadlock-api.com), a community project. Please consider supporting them.

This project is not affiliated with Valve Corporation. Deadlock and the hero and item names are Valve trademarks.
