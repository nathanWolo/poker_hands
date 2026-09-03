from engine import db
from tests.hh import fold_preflop, parse


def test_insert_ignores_duplicate_ids(conn):
    hand = parse(fold_preflop("DUP", "2026/08/01 12:00:00"))
    first = db.insert_hands(conn, [hand])
    second = db.insert_hands(conn, [hand])
    assert first == {"inserted": 1, "skipped": 0, "errors": 0}
    assert second == {"inserted": 0, "skipped": 1, "errors": 0}
    assert db.hand_count(conn) == 1


def test_insert_skips_duplicate_ids_in_same_batch(conn):
    a = parse(fold_preflop("DUP", "2026/08/01 12:00:00"))
    b = parse(fold_preflop("DUP", "2026/08/01 12:00:00"))
    stats = db.insert_hands(conn, [a, b])
    assert stats["inserted"] == 1
    assert stats["skipped"] == 1
    assert db.hand_count(conn) == 1


def test_rebuild_sessions_splits_on_gap(conn):
    early = parse(fold_preflop("A", "2026/08/01 12:00:00"))
    soon = parse(fold_preflop("B", "2026/08/01 12:10:00"))
    later = parse(fold_preflop("C", "2026/08/01 13:00:00"))
    db.insert_hands(conn, [early, soon, later])
    n = db.rebuild_sessions(conn, gap_sec=20 * 60)
    assert n == 2
    rows = conn.execute(
        "SELECT hands, duration_sec FROM sessions ORDER BY start_ts"
    ).fetchall()
    assert [r["hands"] for r in rows] == [2, 1]
    # A→B is 10 minutes
    assert rows[0]["duration_sec"] == 10 * 60
    ids = conn.execute(
        "SELECT id, session_id FROM hands ORDER BY ts"
    ).fetchall()
    assert ids[0]["session_id"] == ids[1]["session_id"]
    assert ids[2]["session_id"] != ids[0]["session_id"]
