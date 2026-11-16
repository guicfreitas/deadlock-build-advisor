"""Short sounds for the events a player should not miss. Windows only (winsound, stdlib);
anywhere else it does nothing. Never raises: a missing sound device must not break a match.

The sound is `sounds/notify.wav` (Kenney "Interface Sounds" confirmation_001, CC0; see
sounds/LICENSE-kenney.txt). If the file is missing, a bell-like chime is synthesized instead
(a few harmonics, soft attack, long exponential decay)."""
from __future__ import annotations

import io
import math
import struct
import sys
import threading
import wave
from functools import lru_cache
from importlib import resources

RATE = 44100

# kind -> [(note frequency Hz, start offset s), ...]; each note rings for ~0.9 s
CHIMES = {
    "ready": [(659.3, 0.0), (987.8, 0.16), (1318.5, 0.32)],   # E5 B5 E6: bright rising "done"
    "respawn": [(784.0, 0.0), (587.3, 0.20)],                  # G5 D5: softer falling "heads up"
}
HARMONICS = ((1, 1.0), (2, 0.35), (3, 0.12), (4.2, 0.08))     # partial, weight


@lru_cache(maxsize=None)
def wav_bytes(kind: str) -> bytes | None:
    """The sound to play for `kind`: the bundled file, else the synthesized chime."""
    if kind not in CHIMES:
        return None
    try:
        return (resources.files("deadlock_advisor") / "sounds" / "notify.wav").read_bytes()
    except OSError:
        return render(kind)


@lru_cache(maxsize=None)
def render(kind: str) -> bytes | None:
    """A mono 16-bit WAV file (bytes) for the chime, or None for an unknown kind."""
    notes = CHIMES.get(kind)
    if not notes:
        return None
    total = max(start for _, start in notes) + 0.9
    n = int(total * RATE)
    mix = [0.0] * n
    for freq, start in notes:
        s0 = int(start * RATE)
        for i in range(min(int(0.9 * RATE), n - s0)):
            t = i / RATE
            env = min(1.0, t / 0.004) * math.exp(-t * 5.5)    # 4 ms attack: no click
            mix[s0 + i] += env * sum(w * math.sin(2 * math.pi * freq * p * t) for p, w in HARMONICS)
    peak = max(abs(x) for x in mix) or 1.0
    pcm = struct.pack(f"<{n}h", *(int(x / peak * 0.6 * 32767) for x in mix))   # 60 %: not startling
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def play(kind: str) -> None:
    """Play a chime in the background; returns at once."""
    if kind not in CHIMES or sys.platform != "win32":
        return
    threading.Thread(target=_play, args=(kind,), daemon=True, name="sound").start()


def _play(kind: str) -> None:
    try:
        import winsound
        winsound.PlaySound(wav_bytes(kind), winsound.SND_MEMORY)   # blocks this thread until done
    except Exception:  # noqa: BLE001 - no sound device, RDP session, ...
        pass
