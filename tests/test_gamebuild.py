import base64

from deadlock_advisor import gamebuild as g

ABIL = [3692321247, 1568845221, 536278136, 2396527575]


def _fields(msg: bytes) -> dict:
    out: dict = {}
    for f, _, v in g.parse_message(msg):
        out.setdefault(f, []).append(v)
    return out


def test_varint_matches_the_game_encoding():
    # a currency change exactly as the game wrote it: ability, type 2, delta -1 (10-byte varint)
    game = bytes.fromhex("08dfb3d1e00d1002") + b"\x18" + b"\xff" * 9 + b"\x01"
    ours = g._uint(1, ABIL[0]) + g._uint(2, 2) + g._uint(3, -1)
    assert ours == game


def test_zstd_raw_frame_roundtrip():
    for data in (b"", b"abc", bytes(range(256)) * 600):  # last one spans two raw blocks
        frame = g.zstd_raw_frame(data)
        assert frame[:4] == g.ZSTD_MAGIC
        assert g.zstd_raw_unframe(frame) == data


def test_ability_order_costs():
    seq = [ABIL[0], ABIL[1], ABIL[2], ABIL[3], ABIL[2], ABIL[2], ABIL[2], ABIL[2]]
    changes = g.ability_order_changes(seq)
    assert changes[:4] == [(a, g.UNLOCK, -1) for a in ABIL]
    assert changes[4:] == [(ABIL[2], g.UPGRADE, -1), (ABIL[2], g.UPGRADE, -2), (ABIL[2], g.UPGRADE, -5)]


def test_share_code_has_the_fields_paste_needs():
    b = g.HeroBuild(79, "Teste", "desc", [g.Category("Lane", [1, 2, 3], "x", annotations={1: "nota"})],
                    g.ability_order_changes(ABIL), author_account_id=157672295, timestamp=1793473046)
    raw = g.zstd_raw_unframe(base64.b64decode(b.share_code()))
    top = _fields(raw)
    # "Colar guia" drops builds without these (seen in game 2026-11-12)
    for f in (1, 2, 3, 4, 9, 13):
        assert f in top, f
    assert top[2] == [79] and top[3] == [157672295] and top[4] == top[13] == [1793473046]
    assert top[5] == [b"Teste"]
    details = _fields(top[10][0])
    cat = _fields(details[1][0])
    assert [_fields(m)[1][0] for m in cat[1]] == [1, 2, 3]
    assert _fields(cat[1][0])[2] == [b"nota"]
    assert 4 in cat and 5 in cat  # without a size the game draws an empty-looking box
    assert len(g.parse_message(details[2][0])) == 4


def test_box_size_fits_item_count():
    one_row = g.Category("a", [1, 2, 3, 4], full_row=False).box()
    assert 330 < one_row[0] < 350 and 155 < one_row[1] < 165  # game: 4 items -> 342 x 160
    two_rows = g.Category("b", list(range(12))).box()
    assert two_rows[1] > one_row[1] + 100
    narrow = lambda desc: g.Category("c", [1], desc, full_row=False).box()[1]
    assert narrow("with description") > narrow("")
    assert g.Category("c", [1], "inline").box()[1] == g.Category("c", [1]).box()[1]
    assert g.Category("d", [1, 2]).box()[0] == g.FULL_ROW_W  # stacked by default


def test_from_recommendation():
    item = lambda i, lift=2.0: {"id": i, "lift": lift}
    rec = {"hero": {"id": 79, "name": "Rem"},
           "lane_enemies": [{"id": 1, "name": "Haze"}, {"id": 2, "name": "Abrams"}],
           "enemies": [{"id": 1, "name": "Haze", "counters": [item(10, 3.5), item(20)]}],
           "lane_build": [item(10), item(11)], "lane_cost": 2400,
           "full_build": {"early": [item(10), item(11)], "mid": [item(12)], "late": []}}
    b = g.from_recommendation(rec, 157672295)
    assert b.name == "Advisor: Rem vs Haze e Abrams"
    names = [c.name for c in b.categories]
    assert names == ["Lane: contra Haze e Abrams", g.MID_GAME, g.SITUATIONAL]  # empty late is skipped
    counters = b.categories[-1]
    assert counters.optional and counters.items == [20]  # 10 is already in the lane build
    assert counters.annotations[20].startswith("Contra Haze")
    assert b.share_code()
