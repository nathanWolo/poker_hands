from engine.db import date_sql_bound, filters_sql, insert_hands, rebuild_sessions
from engine.stats import summary
from tests.conftest import seed_dated_folds, seed_mixed
from tests.hh import fold_preflop, parse


def _ids(conn, args):
    where, params = filters_sql(args)
    rows = conn.execute(f"SELECT id FROM hands WHERE {where} ORDER BY id", params).fetchall()
    return [r["id"] for r in rows]


def test_date_sql_bound_converts_iso_to_slash_played_at():
    assert date_sql_bound("2026-08-01") == "2026/08/01 00:00:00"
    assert date_sql_bound("2026-08-01", end_of_day=True) == "2026/08/01 23:59:59"
    assert date_sql_bound("2026/08/01") == "2026/08/01 00:00:00"
    assert date_sql_bound("") is None
    assert date_sql_bound("not-a-date") is None
    assert date_sql_bound("2026-13-40") is None


def test_iso_from_to_match_slash_played_at(conn):
    """HTML <input type=date> sends YYYY-MM-DD; HH files store YYYY/MM/DD."""
    seed_dated_folds(conn)
    assert _ids(conn, {}) == ["RC-AUG10", "RC-AUG26", "RC-JUL"]

    # Range that should include only Aug 10.
    assert _ids(conn, {"from": "2026-08-01", "to": "2026-08-15"}) == ["RC-AUG10"]

    # Inclusive on both ends.
    assert _ids(conn, {"from": "2026-08-10", "to": "2026-08-10"}) == ["RC-AUG10"]

    # From only: drop July.
    assert _ids(conn, {"from": "2026-08-01"}) == ["RC-AUG10", "RC-AUG26"]

    # To only: drop late August.
    assert _ids(conn, {"to": "2026-08-10"}) == ["RC-AUG10", "RC-JUL"]

    # Day after Aug 10 excludes that hand.
    assert _ids(conn, {"from": "2026-08-11"}) == ["RC-AUG26"]


def test_iso_to_does_not_wipe_all_hands(conn):
    """Regression: slash timestamps compare greater than ISO, so to=YYYY-MM-DD matched nothing."""
    seed_dated_folds(conn)
    ids = _ids(conn, {"to": "2026-08-15"})
    assert ids == ["RC-AUG10", "RC-JUL"]
    assert "RC-AUG26" not in ids


def test_game_and_position_and_result_filters(conn):
    seed_mixed(conn)
    assert _ids(conn, {"game": "PLO"}) == ["PL-1"]
    assert _ids(conn, {"game": "NLHE"}) == [
        "RC-AUG10",
        "RC-AUG26",
        "RC-JUL",
        "RC-STEAL",
        "RC-WIN",
    ]
    assert _ids(conn, {"position": "BB"}) == ["RC-WIN"]
    assert _ids(conn, {"position": "BTN"}) == [
        "PL-1",
        "RC-AUG10",
        "RC-AUG26",
        "RC-JUL",
        "RC-STEAL",
    ]
    assert _ids(conn, {"result": "won"}) == ["RC-STEAL", "RC-WIN"]
    assert "RC-JUL" in _ids(conn, {"result": "even"})
    assert _ids(conn, {"hand": "AA"}) == ["RC-AUG26"]
    assert _ids(conn, {"q": "Qs Kc"}) == ["RC-WIN"]


def test_summary_respects_date_filter(conn):
    seed_dated_folds(conn)
    all_h = summary(conn, {"game": "NLHE"})
    mid = summary(conn, {"game": "NLHE", "from": "2026-08-01", "to": "2026-08-15"})
    assert all_h["hands"] == 3
    assert mid["hands"] == 1
    assert mid["first_hand"].startswith("2026/08/10")
    assert mid["last_hand"].startswith("2026/08/10")


def test_sessions_join_still_accepts_date_filter(conn):
    insert_hands(conn, [parse(fold_preflop("A", "2026/08/01 12:00:00"))])
    insert_hands(conn, [parse(fold_preflop("B", "2026/08/20 12:00:00"))])
    rebuild_sessions(conn, gap_sec=60)
    where, params = filters_sql({"from": "2026-08-15", "to": "2026-08-20"})
    n = conn.execute(
        f"""
        SELECT COUNT(h.id) AS n
        FROM sessions s
        JOIN hands h ON h.session_id = s.id
        WHERE {where}
        """,
        params,
    ).fetchone()["n"]
    assert n == 1
