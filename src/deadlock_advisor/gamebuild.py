"""Export a recommendation as a Deadlock "share code" for the in-game Hero Builds editor.

The game's "Copy to Clipboard" / "Paste Build" buttons (Hero Builds -> Explorar guias)
use base64(zstd(protobuf CMsgHeroBuild)). We only put text on the clipboard: the player
clicks "Colar guia" themselves, so nothing touches the game process or its files.

Field numbers were read from a build the game itself copied (2026-11-12) and match the
JSON field order of deadlock-api's /v1/builds:

  CMsgHeroBuild   1 hero_build_id  2 hero_id  3 author_account_id  4 last_updated_timestamp
                  5 name  6 description  7 language  8 version  9 origin_build_id
                  10 details  11 tags (repeated)
  Details         1 mod_categories (repeated)  2 ability_order
  ModCategory     1 mods (repeated)  2 name  3 description  4 width (float)  5 height (float)
                  6 optional (bool)
  Mod             1 ability_id  2 annotation  3 required_flex_slots  4 sell_priority
                  5 imbue_target_ability_id
  AbilityOrder    1 currency_changes (repeated)
  CurrencyChange  1 ability_id  2 currency_type  3 delta (int32)  4 annotation

Currency types: 2 = the point that unlocks an ability, 1 = ability points spent on upgrades.

"Paste Build" silently drops a build that lacks the header fields the game always writes
(1, 3, 4, 9, 13: verified 2026-11-12, it pasted only an empty category). Field 13 holds the
same timestamp as field 4 in every build the game copied.
"""
from __future__ import annotations

import base64
import struct
import time
from dataclasses import dataclass, field

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
UNLOCK, UPGRADE = 2, 1          # CurrencyChange.currency_type
UPGRADE_COSTS = (1, 2, 5)       # ability points per upgrade tier
LANGUAGE_BRAZILIAN = 22         # what the game wrote for a pt-BR client
_MAX_RAW_BLOCK = 128 * 1024
# Category box layout, fitted on builds the game copied: ~84 px per item card plus padding,
# ~160 px for one row of cards and ~122 px per extra row. Without width/height the game
# draws a box too small to show the items.
ITEM_W, BOX_PAD, ROW_H, EXTRA_ROW_H, PER_ROW = 84.0, 12.0, 160.8, 122.0, 7
DESC_H = 48.0                   # a description in a narrow box wraps under the title, pushing the cards down
# The format has no box position: the game flows boxes left to right. Boxes wider than half
# the panel (~1150 units at 1080p) can't share a row, so they stack top to bottom.
FULL_ROW_W = 900.0


# --------------------------------------------------------------------------- protobuf
def _varint(n: int) -> bytes:
    n &= (1 << 64) - 1          # negative int32/int64 are sign-extended to 10 bytes
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _key(field_no: int, wire: int) -> bytes:
    return _varint(field_no << 3 | wire)


def _uint(field_no: int, n: int | None) -> bytes:
    return b"" if n is None else _key(field_no, 0) + _varint(n)


def _bytes(field_no: int, data: bytes | str | None) -> bytes:
    if data is None:
        return b""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return _key(field_no, 2) + _varint(len(data)) + data


def _float(field_no: int, x: float | None) -> bytes:
    return b"" if x is None else _key(field_no, 5) + struct.pack("<f", x)


def read_varint(b: bytes, i: int) -> tuple[int, int]:
    r = s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        s += 7
        if c < 0x80:
            return r, i


def parse_message(b: bytes) -> list[tuple[int, int, int | bytes]]:
    """Generic protobuf reader: [(field, wire_type, value)], used by tests and debugging."""
    i, out = 0, []
    while i < len(b):
        k, i = read_varint(b, i)
        f, t = k >> 3, k & 7
        if t == 0:
            v, i = read_varint(b, i)
        elif t == 2:
            n, i = read_varint(b, i)
            v, i = b[i:i + n], i + n
        elif t == 5:
            v, i = int.from_bytes(b[i:i + 4], "little"), i + 4
        elif t == 1:
            v, i = int.from_bytes(b[i:i + 8], "little"), i + 8
        else:
            raise ValueError(f"unsupported wire type {t}")
        out.append((f, t, v))
    return out


# --------------------------------------------------------------------------- zstd
def zstd_raw_frame(data: bytes) -> bytes:
    """A valid zstd frame made of uncompressed ("raw") blocks: no compressor needed.

    Frame header descriptor 0xA0 = 4-byte Frame_Content_Size + Single_Segment, no checksum,
    no dictionary. Each block header is 3 bytes: last-block bit, type 0 (raw), 21-bit size.
    """
    out = bytearray(ZSTD_MAGIC + b"\xa0" + struct.pack("<I", len(data)))
    chunks = [data[i:i + _MAX_RAW_BLOCK] for i in range(0, len(data), _MAX_RAW_BLOCK)] or [b""]
    for n, chunk in enumerate(chunks):
        last = n == len(chunks) - 1
        out += (len(chunk) << 3 | int(last)).to_bytes(3, "little") + chunk
    return bytes(out)


def zstd_raw_unframe(frame: bytes) -> bytes:
    """Inverse of zstd_raw_frame (raw/RLE blocks only; the game's own codes are compressed)."""
    if frame[:4] != ZSTD_MAGIC:
        raise ValueError("not a zstd frame")
    fhd = frame[4]
    fcs_size = {0: 1 if fhd & 0x20 else 0, 1: 2, 2: 4, 3: 8}[fhd >> 6]
    i = 5 + (0 if fhd & 0x20 else 1) + (0, 1, 2, 4)[fhd & 3] + fcs_size
    out = bytearray()
    while True:
        h = int.from_bytes(frame[i:i + 3], "little")
        i += 3
        last, btype, size = h & 1, (h >> 1) & 3, h >> 3
        if btype == 0:
            out += frame[i:i + size]
            i += size
        elif btype == 1:
            out += frame[i:i + 1] * size
            i += 1
        else:
            raise ValueError("compressed zstd block: needs a real zstd decoder")
        if last:
            return bytes(out)


# --------------------------------------------------------------------------- model
@dataclass
class Category:
    name: str
    items: list[int]                     # item ids (the API's "id" == the game's ability_id)
    description: str = ""
    optional: bool = False
    annotations: dict[int, str] = field(default_factory=dict)
    width: float | None = None           # None = sized from the item count
    full_row: bool = True                # stack categories vertically (lane, mid, late...)
    height: float | None = None

    def box(self) -> tuple[float, float]:
        n = max(len(self.items), 2)      # keep room for the title on 1-item boxes
        rows = -(-n // PER_ROW)
        w = self.width or ITEM_W * min(n, PER_ROW) + BOX_PAD
        if self.full_row and not self.width:
            w = max(w, FULL_ROW_W)
        # a description only wraps under the title in narrow boxes; full rows show it inline
        wraps = self.description and not self.full_row
        h = self.height or ROW_H + EXTRA_ROW_H * (rows - 1) + (DESC_H if wraps else 0)
        return w, h


@dataclass
class HeroBuild:
    hero_id: int
    name: str
    description: str = ""
    categories: list[Category] = field(default_factory=list)
    ability_order: list[tuple[int, int, int]] = field(default_factory=list)  # (ability_id, type, delta)
    language: int = LANGUAGE_BRAZILIAN
    author_account_id: int = 0
    hero_build_id: int = 0               # 0 = derive one from the timestamp
    tags: list[int] = field(default_factory=list)
    timestamp: int = 0                   # 0 = now

    def to_protobuf(self) -> bytes:
        cats = b""
        for c in self.categories:
            mods = b"".join(_bytes(1, _uint(1, item) + _bytes(2, c.annotations.get(item)))
                            for item in c.items)
            w, h = c.box()
            cats += _bytes(1, mods + _bytes(2, c.name) + _bytes(3, c.description)
                           + _float(4, w) + _float(5, h)
                           + (_uint(6, 1) if c.optional else b""))
        order = b"".join(_bytes(1, _uint(1, a) + _uint(2, t) + _uint(3, d))
                         for a, t, d in self.ability_order)
        details = cats + (_bytes(2, order) if order else b"")
        ts = self.timestamp or int(time.time())
        build_id = self.hero_build_id or ts % 1_000_000_000
        return (_uint(1, build_id) + _uint(2, self.hero_id) + _uint(3, self.author_account_id)
                + _uint(4, ts) + _bytes(5, self.name) + _bytes(6, self.description)
                + _uint(7, self.language) + _uint(8, 1) + _uint(9, build_id)
                + _bytes(10, details) + b"".join(_uint(11, t) for t in self.tags) + _uint(13, ts))

    def share_code(self) -> str:
        return base64.b64encode(zstd_raw_frame(self.to_protobuf())).decode("ascii")


def ability_order_changes(sequence: list[int], unlocks: int = 4) -> list[tuple[int, int, int]]:
    """Turn "which ability gets the next point" into the game's currency changes.

    The first time an ability appears in `sequence` it is unlocked (one UNLOCK point); each
    later appearance buys its next upgrade tier, which costs 1, 2 and 5 ability points
    (verified on a build the game copied). Extra appearances past tier 3 are dropped.
    """
    tiers: dict[int, int] = {}
    out = []
    for ability in sequence:
        if ability not in tiers:
            if len(tiers) >= unlocks:
                continue
            tiers[ability] = 0
            out.append((ability, UNLOCK, -1))
        elif tiers[ability] < len(UPGRADE_COSTS):
            out.append((ability, UPGRADE, -UPGRADE_COSTS[tiers[ability]]))
            tiers[ability] += 1
    return out


# --------------------------------------------------------------------------- from the engine
MID_GAME, LATE_GAME = "#Citadel_HeroBuilds_MidGame", "#Citadel_HeroBuilds_LateGame"  # localized by the game
SITUATIONAL = "Situacional"
MAX_NAME = 60


def _lift_note(item: dict) -> str | None:
    lift = item.get("lift")
    return f"{lift:+.1f}% de win rate nesta partida" if lift else None


def from_recommendation(rec: dict, account_id: int | None = None) -> HeroBuild:
    """Turn Recommender.recommend() output into a pasteable Hero Build."""
    lane_names = " e ".join(e["name"] for e in rec.get("lane_enemies", []))
    name = f"Advisor: {rec['hero']['name']}" + (f" vs {lane_names}" if lane_names else "")
    cats: list[Category] = []

    def add(title: str, items: list[dict], description: str = "", optional: bool = False):
        if items:
            cats.append(Category(title, [i["id"] for i in items], description, optional,
                                 {i["id"]: n for i in items if (n := _lift_note(i))}))

    add(f"Lane: contra {lane_names}" if lane_names else "Lane", rec.get("lane_build", []),
        f"{rec.get('lane_cost', 0)} almas, da esquerda para a direita")
    full = rec.get("full_build", {})
    add(MID_GAME, full.get("mid", []))
    add(LATE_GAME, full.get("late", []))

    taken = {i for c in cats for i in c.items}
    counters: list[dict] = []
    notes: dict[int, str] = {}
    for enemy in rec.get("enemies", []):
        for item in enemy.get("counters", []):
            if item["id"] not in taken:
                taken.add(item["id"])
                counters.append(item)
                notes[item["id"]] = f"Contra {enemy['name']}: {item['lift']:+.1f}% de win rate"
    if counters:
        cats.append(Category(SITUATIONAL, [i["id"] for i in counters],
                             "counters contra os inimigos", True, notes))

    enemies = ", ".join(e["name"] for e in rec.get("enemies", []))
    desc = ("Gerado pelo Deadlock Build Advisor"
            + (f" contra {enemies}" if enemies else "") + ".")
    return HeroBuild(rec["hero"]["id"], name[:MAX_NAME], desc, cats,
                     author_account_id=account_id or 0)
