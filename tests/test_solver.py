from engine.solver import (
    actor_label,
    build_commands,
    combo_keys,
    format_board,
    lookup_combo,
    spot_from_hand,
    status,
    summarize_result,
)
from tests.hh import fold_preflop, hero_bb_defend_win, parse


def test_format_board_and_combo_keys():
    assert format_board(["Qs", "Jh", "2h"]) == "Qs,Jh,2h"
    assert format_board("Qs Jh 2h") == "Qs,Jh,2h"
    assert combo_keys("Ah Kd") == ["AhKd", "KdAh"]


def test_lookup_combo_either_order():
    table = {"AhKd": [0.8, 0.2]}
    key, freqs = lookup_combo(table, "Kd Ah")
    assert key == "AhKd"
    assert freqs[0] == 0.8


def test_actor_label_oop_is_player_1():
    assert actor_label(1) == "oop"
    assert actor_label(0) == "ip"


def test_summarize_result_root_and_hero():
    tree = {
        "player": 1,
        "actions": ["CHECK", "BET 2.0"],
        "strategy": {
            "actions": ["CHECK", "BET 2.0"],
            "strategy": {
                "AhKd": [0.25, 0.75],
                "4c3c": [0.9, 0.1],
            },
        },
        "childrens": {
            "CHECK": {
                "node_type": "action_node",
                "player": 0,
                "actions": ["CHECK", "BET 2.0"],
                "strategy": {"strategy": {"QsQc": [0.1, 0.9]}, "actions": ["CHECK", "BET 2.0"]},
            }
        },
    }
    out = summarize_result(tree, "Ah Kd")
    assert out["root"]["actor"] == "oop"
    assert out["root"]["hero"]["combo"] == "AhKd"
    assert out["root"]["hero"]["freqs"][1] == 0.75
    assert out["root"]["average"]["CHECK"] == 0.575
    assert out["after_check"]["actor"] == "ip"


def test_build_commands_uses_slash_dump_path(tmp_path):
    text = build_commands(
        {"board": ["Qs", "8d", "7h"], "pot": 4, "effective_stack": 10, "range_ip": "T9s", "range_oop": "JTs"},
        tmp_path / "out.json",
        preset="fast",
    )
    assert "set_board Qs,8d,7h" in text
    assert "set_range_ip T9s" in text
    assert "dump_result " in text
    assert " " not in text.split("dump_result ", 1)[1].splitlines()[0]


def test_spot_from_hand_heads_up_flop():
    hand = parse(hero_bb_defend_win("H1", "2026/08/01 12:00:00"))
    spot = spot_from_hand(hand)
    assert spot["ok"] is True
    assert spot["street"] == "flop"
    assert spot["board"][:3] == ["4h", "3s", "Kd"]
    assert spot["hero_role"] == "oop"
    assert spot["oop"]["position"] == "BB"
    assert spot["ip"]["position"] == "BTN"
    assert spot["pot"] > 0
    assert spot["effective_stack"] > 0


def test_spot_from_hand_rejects_multiway_fold():
    hand = parse(fold_preflop("H1", "2026/08/01 12:00:00"))
    spot = spot_from_hand(hand)
    assert spot["ok"] is False


def test_status_reports_install_layout():
    st = status()
    assert "installed" in st
    assert "presets" in st
