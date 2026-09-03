from engine.parser import (
    assign_positions,
    money_cents,
    parse_file,
    parse_hand,
    Seat,
    starting_hand_key,
)
from tests.hh import (
    fold_preflop,
    hero_bb_defend_win,
    hero_faces_3bet_folds,
    hero_steal,
    parse,
)


def test_split_and_parse_file():
    text = (
        fold_preflop("RC1", "2026/08/01 12:00:00")
        + "\n"
        + fold_preflop("RC2", "2026/08/02 12:00:00")
    )
    hands = parse_file(text)
    assert [h.id for h in hands] == ["RC1", "RC2"]


def test_parse_hand_rejects_garbage():
    assert parse_hand("not a hand") is None


def test_game_type_nlhe_and_plo():
    nlhe = parse(fold_preflop("H1", "2026/08/01 12:00:00"))
    plo = parse(fold_preflop("H2", "2026/08/01 12:00:00", game="Omaha Pot Limit"))
    assert nlhe.game_type == "NLHE"
    assert plo.game_type == "PLO"
    assert nlhe.ts > 0
    assert nlhe.played_at == "2026/08/01 12:00:00"


def test_sixmax_positions_button_seat_1():
    hand = parse(fold_preflop("H1", "2026/08/01 12:00:00"))
    by_seat = {s.seat: s.position for s in hand.seats}
    assert by_seat == {1: "BTN", 2: "SB", 3: "BB", 4: "UTG", 5: "HJ", 6: "CO"}
    assert hand.hero_seat().position == "BTN"


def test_assign_positions_rotates_with_button():
    seats = [Seat(seat=i, name=f"p{i}", stack=500) for i in range(1, 7)]
    assign_positions(seats, button=4)
    assert {s.seat: s.position for s in seats}[4] == "BTN"
    assert {s.seat: s.position for s in seats}[5] == "SB"
    assert {s.seat: s.position for s in seats}[6] == "BB"
    assert {s.seat: s.position for s in seats}[1] == "UTG"


def test_starting_hand_key_order_and_suited():
    assert starting_hand_key(["Ah", "Kd"]) == "AKo"
    assert starting_hand_key(["Kd", "Ah"]) == "AKo"
    assert starting_hand_key(["As", "Ks"]) == "AKs"
    assert starting_hand_key(["9h", "9c"]) == "99"
    assert starting_hand_key(["7s", "2h"]) == "72o"


def test_money_cents():
    assert money_cents("$0.04") == 4
    assert money_cents("raises $0.04 to $0.06") == 4
    assert money_cents(None) == 0


def test_fold_preflop_flags_and_net():
    hand = parse(fold_preflop("H1", "2026/08/01 12:00:00"))
    hf = hand.hero_flags()
    assert hf.vpip == 0
    assert hf.pfr == 0
    assert hf.invested == 0
    assert hf.net == 0
    assert hf.threebet_opp == 1
    assert hf.threebet == 0
    assert hf.fold_to_3bet == 0


def test_raise_to_uses_chips_added_not_raise_by():
    """'raises $0.04 to $0.06' must invest 6c, then uncalled 4c → 2c in, +3c net."""
    hand = parse(hero_steal("H1", "2026/08/01 12:00:00"))
    hf = hand.hero_flags()
    raise_act = next(a for a in hand.actions if a.type == "raise" and a.player == "Hero")
    assert raise_act.amount == 6
    assert raise_act.to_amount == 6
    assert hf.invested == 2
    assert hf.collected == 5
    assert hf.net == 3
    assert hf.vpip == 1
    assert hf.pfr == 1
    assert hf.steal == 1
    assert hf.steal_opp == 1


def test_fold_to_3bet_on_btn_open():
    hand = parse(hero_faces_3bet_folds("H1", "2026/08/01 12:00:00"))
    hf = hand.hero_flags()
    assert hf.pfr == 1
    assert hf.steal == 1
    assert hf.fold_to_3bet_opp == 1
    assert hf.fold_to_3bet == 1
    assert hf.threebet == 0
    bb = hand.flags["p3"]
    assert bb.threebet == 1
    assert hf.invested == 6
    assert hf.net == -6


def test_showdown_win_rake_and_wtsd():
    hand = parse(hero_bb_defend_win("H1", "2026/08/01 12:00:00"))
    hf = hand.hero_flags()
    assert hand.hero_seat().position == "BB"
    assert hand.rake == 4
    assert hand.jackpot == 3
    assert hand.pot == 94
    assert hf.collected == 87
    assert hf.saw_flop == 1
    assert hf.wtsd == 1
    assert hf.won_sd == 1
    assert hf.vpip == 1
    assert hf.pfr == 0
    assert hf.call_3bet == 1
    # 2+12+11+19 = 44c in
    assert hf.invested == 44
    assert hf.net == 87 - 44
