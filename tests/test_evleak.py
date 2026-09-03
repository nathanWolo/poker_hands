import time

from engine import db, evleak
from engine.parser import Action
from tests.conftest import insert_text, seed_dated_folds
from tests.hh import hero_bb_defend_win, hero_btn_cbet, parse


OOP_TREE = {
    "player": 1,
    "node_type": "action_node",
    "actions": ["CHECK", "BET 15.000000"],
    "strategy": {
        "actions": ["CHECK", "BET 15.000000"],
        "strategy": {
            "QsKc": [1.0, 0.0],
            "AhKd": [0.1, 0.9],
        },
    },
    "childrens": {
        "CHECK": {
            "node_type": "action_node",
            "player": 0,
            "actions": ["CHECK", "BET 20.000000"],
            "strategy": {
                "actions": ["CHECK", "BET 20.000000"],
                "strategy": {"AhKd": [0.25, 0.75]},
            },
        }
    },
}


def test_match_check_and_nearest_bet():
    actions = ["CHECK", "BET 2.000000", "BET 10.000000"]
    chk = Action(street="flop", player="Hero", type="check")
    assert evleak.match_gto_action(chk, actions) == "CHECK"
    bet = Action(street="flop", player="Hero", type="bet", amount=11)
    assert evleak.match_gto_action(bet, actions) == "BET 10.000000"
    fold = Action(street="flop", player="Hero", type="fold")
    assert evleak.match_gto_action(fold, ["CALL", "FOLD"]) == "FOLD"


def test_select_node_oop_root_and_ip_after_check():
    vill = Action(street="flop", player="p3", type="check")
    oop = evleak.select_strategy_node(OOP_TREE, "oop", None)
    assert oop is OOP_TREE
    ip = evleak.select_strategy_node(OOP_TREE, "ip", vill)
    assert ip["player"] == 0
    assert "BET 20.000000" in ip["actions"]


def test_score_combo_mixed_and_out_of_range():
    hero = Action(street="flop", player="Hero", type="check")
    mixed = evleak.score_combo(OOP_TREE, "Qs Kc", hero)
    assert mixed["in_range"] is True
    assert mixed["gto_match"] == "CHECK"
    assert mixed["gto_freq"] == 1.0
    missing = evleak.score_combo(OOP_TREE, "7s 2h", hero)
    assert missing["in_range"] is False
    assert missing["gto_freq"] == 0.0


def test_hero_line_oop_and_ip():
    oop_hand = parse(hero_bb_defend_win("H1", "2026/08/01 12:00:00"))
    act, vill = evleak.hero_line(oop_hand, "flop", "oop", "Hero", "Hero")
    assert act.type == "check"
    assert vill is None

    ip_hand = parse(hero_btn_cbet("H2", "2026/08/01 12:00:00"))
    act, vill = evleak.hero_line(ip_hand, "flop", "ip", "p3", "Hero")
    assert vill.type == "check"
    assert act.type == "bet"


def test_pick_spots_all_returns_every_eligible():
    spots = [
        {"net": -10, "spot": {"pot": 1}, "hand_id": "a"},
        {"net": 5, "spot": {"pot": 9}, "hand_id": "b"},
        {"net": -3, "spot": {"pot": 4}, "hand_id": "c"},
    ]
    all_spots = evleak.pick_spots(spots, 0, by="loss")
    assert [s["hand_id"] for s in all_spots] == ["a", "c", "b"]


def test_decision_replay_index_first_hero_vol_on_street():
    hand = parse(hero_bb_defend_win("H1", "2026/08/01 12:00:00"))
    idx = evleak.decision_replay_index(hand, "flop", "Hero")
    acts = [a for a in hand.actions if a.type in evleak.REPLAY_TYPES]
    assert acts[idx].type == "check"
    assert acts[idx].street == "flop"


def test_collect_and_pick_spots(conn):
    seed_dated_folds(conn)
    insert_text(conn, hero_bb_defend_win("RC-WIN", "2026/08/11 21:00:00"))
    insert_text(conn, hero_btn_cbet("RC-CBET", "2026/08/11 22:00:00"))
    spots = evleak.collect_hu_spots(conn, {"game": "NLHE"})
    assert len(spots) == 2
    roles = {s["spot"]["hero_role"] for s in spots}
    assert roles == {"oop", "ip"}
    picked = evleak.pick_spots(spots, 1, by="pot")
    assert len(picked) == 1


def test_review_spot_uses_cache(conn, monkeypatch):
    insert_text(conn, hero_bb_defend_win("RC-WIN", "2026/08/11 21:00:00"))
    spots = evleak.collect_hu_spots(conn, {"game": "NLHE"})
    item = spots[0]
    key = evleak._cache_key(item["spot"], "audit")
    evleak._store_tree(conn, key, OOP_TREE)

    def boom(*_a, **_k):
        raise AssertionError("solver should not run when the tree is cached")

    monkeypatch.setattr(evleak.solver, "run_solve", boom)
    rec = evleak.review_spot(conn, item, "audit")
    assert rec["ok"] is True
    assert rec["gto_freq"] == 1.0
    assert rec["ev_lost_cents"] == 0
    assert rec["hero_action_type"] == "check"

    # Mixed best action should not count as a leak.
    mixed_tree = {
        "player": 1,
        "actions": ["CHECK", "BET 15.000000"],
        "strategy": {
            "actions": ["CHECK", "BET 15.000000"],
            "strategy": {"QsKc": [0.5, 0.5]},
        },
        "childrens": {},
    }
    evleak._store_tree(conn, key, mixed_tree)
    mixed = evleak.review_spot(conn, item, "audit")
    assert mixed["gto_freq"] == 0.5
    assert mixed["ev_lost_cents"] == 0
    assert mixed["mix"]["actions"] == ["CHECK", "BET 15.000000"]

    fetched = evleak.get_review(conn, "RC-WIN")
    assert fetched["ok"] is True
    assert fetched["decision_index"] is not None
    assert fetched["mix"]["freqs"][0] == 0.5

    report = evleak.leak_report(conn, {"game": "NLHE"})
    assert report["spots"] == 1
    assert report["ev_lost"] == 0
    assert report["worst"][0]["id"] == "RC-WIN"


def test_review_spot_off_tree_bet_counts_as_leak(conn, monkeypatch):
    insert_text(conn, hero_bb_defend_win("RC-WIN", "2026/08/11 21:00:00"))
    item = evleak.collect_hu_spots(conn, {"game": "NLHE"})[0]
    item = dict(item)
    item["hero_act"] = Action(street="flop", player="Hero", type="bet", amount=99, allin=False)
    key = evleak._cache_key(item["spot"], "audit")
    evleak._store_tree(conn, key, OOP_TREE)
    monkeypatch.setattr(evleak.solver, "run_solve", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("cache")))
    rec = evleak.review_spot(conn, item, "audit")
    assert rec["gto_match"] == "BET 15.000000"
    assert rec["gto_freq"] == 0.0
    assert rec["gto_best"] == "CHECK"
    assert rec["ev_lost_cents"] == item["spot"]["pot"]


def test_out_of_range_is_not_full_pot_leak(conn, monkeypatch):
    insert_text(conn, hero_bb_defend_win("RC-WIN", "2026/08/11 21:00:00"))
    item = evleak.collect_hu_spots(conn, {"game": "NLHE"})[0]
    tree = {
        "player": 1,
        "actions": ["CHECK", "BET 15.000000"],
        "strategy": {"actions": ["CHECK", "BET 15.000000"], "strategy": {"AhKd": [1.0, 0.0]}},
        "childrens": {},
    }
    evleak._store_tree(conn, evleak._cache_key(item["spot"], "audit"), tree)
    monkeypatch.setattr(evleak.solver, "run_solve", lambda *_a, **_k: {"ok": False})
    rec = evleak.review_spot(conn, item, "audit")
    assert rec["in_range"] == 0
    assert rec["ev_lost_cents"] == 0
    assert "not in the default" in rec["note"]


def test_analyze_empty_filter_does_not_solve(tmp_path, monkeypatch):
    path = tmp_path / "poker.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    conn = db.init(db.connect(path))
    seed_dated_folds(conn)
    conn.close()
    evleak.reset_job()
    out = evleak.start_analyze({"game": "NLHE"}, limit=5, preset="audit")
    assert out["ok"] is True
    status = None
    for _ in range(80):
        status = evleak.job_status()
        if status["state"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert status["state"] == "done"
    assert status["total"] == 0
    evleak.reset_job()


def test_reset_db_clears_solver_tables(conn):
    conn.execute(
        "INSERT INTO solver_reviews (hand_id, ev_lost_cents, updated_at) VALUES ('X', 1, 't')"
    )
    conn.execute("INSERT INTO solver_cache (cache_key, result_json, created_at) VALUES ('k', '{}', 't')")
    conn.commit()
    db.reset_db(conn)
    assert conn.execute("SELECT COUNT(*) AS n FROM solver_reviews").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM solver_cache").fetchone()["n"] == 0
