"""Short beeps for the events a player should not miss. Windows only (winsound, stdlib);
anywhere else it does nothing. Never raises: a missing sound device must not break a match."""
from __future__ import annotations

import sys
import threading

# kind -> [(frequency Hz, milliseconds), ...]
TONES = {
    "ready": [(880, 140), (1320, 220)],     # build ready to copy: two rising notes
    "respawn": [(660, 120), (660, 120)],    # jungle / crates coming back: two short beeps
}


def play(kind: str) -> None:
    """Play a tone in the background; returns at once."""
    tones = TONES.get(kind)
    if not tones or sys.platform != "win32":
        return
    threading.Thread(target=_beep, args=(tones,), daemon=True, name="sound").start()


def _beep(tones) -> None:
    try:
        import winsound
        for freq, ms in tones:
            winsound.Beep(freq, ms)
    except Exception:  # noqa: BLE001 - no sound device, RDP session, ...
        pass
