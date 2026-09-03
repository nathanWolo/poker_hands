from engine.stats import graph, hero_rake_paid_cents, leaks, summary
from tests.conftest import seed_dated_folds, seed_mixed
from tests.hh import hero_bb_defend_win, hero_steal, parse


def test_hero_rake_paid_only_when_hero_collected():
    assert hero_rake_paid_cents({
        "hero_collected": 0, "pot": 94, "rake": 4, "jackpot": 3,
        "bingo": 0, "fortune": 0, "tax": 0,
    }) == 0
    # Won the whole distributed pot: share equals all fees.
    assert hero_rake_paid_cents({
        "hero_collected": 87, "pot": 94, "rake": 4, "jackpot": 3,
        "bingo": 0, "fortune": 0, "tax": 0,
    }) == 7
    # Half the distributed pot.
    assert hero_rake_paid_cents({
        "hero_collected": 40, "pot": 94, "rake": 4, "jackpot": 3,
        "bingo": 0, "fortune": 0, "tax": 0,
    }) == round(7 * 40 / 87)


def test_summary_bb100_before_and_after_rake(conn):
    from engine.db import insert_hands

    steal = parse(hero_steal("S1", "2026/08/10 12:00:00"))
    win = parse(hero_bb_defend_win("W1", "2026/08/11 12:00:00"))
    insert_hands(conn, [steal, win])

    hud = summary(conn, {"game": "NLHE"})
    assert hud["hands"] == 2
    # steal +3c, showdown +43c
    assert hud["net"] == 0.46
    # fees 7c from the won pot
    assert hud["rake_paid"] == 0.07
    # bb_sum = 2 + 2 = 4 cents; after = 46/4*100, before = 53/4*100
    assert hud["bb100"] == round(100.0 * 46 / 4, 2)
    assert hud["bb100_before"] == round(100.0 * 53 / 4, 2)


def test_summary_empty_db(conn):
    hud = summary(conn, {})
    assert hud["hands"] == 0
    assert hud["net"] == 0
    assert hud["bb100"] == 0
    assert hud["bb100_before"] == 0
    assert hud["rake_paid"] == 0


def test_graph_gross_is_net_plus_rake_paid(conn):
    from engine.db import insert_hands

    insert_hands(conn, [
        parse(hero_steal("S1", "2026/08/10 12:00:00")),
        parse(hero_bb_defend_win("W1", "2026/08/11 12:00:00")),
    ])
    g = graph(conn, {})
    assert g["hands"] == 2
    assert g["net"] == 0.46
    assert g["rake_paid"] == 0.07
    assert g["gross"] == 0.53
    assert g["points"][-1]["net"] == 0.46
    assert g["points"][-1]["gross"] == 0.53


def test_leaks_flag_low_vpip(conn):
    seed_dated_folds(conn)
    findings = {f["key"]: f for f in leaks(conn, {"game": "NLHE"})}
    assert findings["vpip"]["status"] == "low"
    assert findings["pfr"]["status"] == "low"
    assert "missing playable" in findings["vpip"]["note"]


def test_date_filter_changes_overview_totals(conn):
    seed_mixed(conn)
    all_h = summary(conn, {"game": "all"})
    week = summary(conn, {"game": "all", "from": "2026-08-10", "to": "2026-08-11"})
    assert all_h["hands"] > week["hands"]
    assert week["hands"] == 3  # fold Aug10, steal Aug10, win Aug11
