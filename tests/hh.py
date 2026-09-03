"""Builders for GGPoker-style cash hand histories used in tests."""

from engine.parser import parse_hand


def fold_preflop(
    hid: str,
    dt: str,
    *,
    hero_cards: str = "7s 2h",
    game: str = "Hold'em No Limit",
) -> str:
    """Hero on the button folds to a UTG open. Net 0."""
    return f"""Poker Hand #{hid}: {game} ($0.01/$0.02) - {dt}
Table 'RushAndCash1' 6-max Seat #1 is the button
Seat 1: Hero ($5 in chips)
Seat 2: p2 ($5 in chips)
Seat 3: p3 ($5 in chips)
Seat 4: p4 ($5 in chips)
Seat 5: p5 ($5 in chips)
Seat 6: p6 ($5 in chips)
p2: posts small blind $0.01
p3: posts big blind $0.02
*** HOLE CARDS ***
Dealt to Hero [{hero_cards}]
Dealt to p2 
Dealt to p3 
Dealt to p4 
Dealt to p5 
Dealt to p6 
p4: raises $0.04 to $0.06
p5: folds
p6: folds
Hero: folds
p2: folds
p3: folds
Uncalled bet ($0.04) returned to p4
*** SHOWDOWN ***
p4 collected $0.05 from pot
*** SUMMARY ***
Total pot $0.05 | Rake $0 | Jackpot $0 | Bingo $0 | Fortune $0 | Tax $0
Seat 1: Hero (button) folded before Flop (didn't bet)
"""


def hero_steal(hid: str, dt: str, *, hero_cards: str = "Ah Kd") -> str:
    """BTN open, blinds fold. Raise-to accounting: invested 2c, collected 5c, net +3c."""
    return f"""Poker Hand #{hid}: Hold'em No Limit ($0.01/$0.02) - {dt}
Table 'RushAndCash1' 6-max Seat #1 is the button
Seat 1: Hero ($5 in chips)
Seat 2: p2 ($5 in chips)
Seat 3: p3 ($5 in chips)
Seat 4: p4 ($5 in chips)
Seat 5: p5 ($5 in chips)
Seat 6: p6 ($5 in chips)
p2: posts small blind $0.01
p3: posts big blind $0.02
*** HOLE CARDS ***
Dealt to Hero [{hero_cards}]
Dealt to p2 
Dealt to p3 
Dealt to p4 
Dealt to p5 
Dealt to p6 
p4: folds
p5: folds
p6: folds
Hero: raises $0.04 to $0.06
p2: folds
p3: folds
Uncalled bet ($0.04) returned to Hero
*** SHOWDOWN ***
Hero collected $0.05 from pot
*** SUMMARY ***
Total pot $0.05 | Rake $0 | Jackpot $0 | Bingo $0 | Fortune $0 | Tax $0
Seat 1: Hero (button) collected ($0.05)
"""


def hero_bb_defend_win(hid: str, dt: str) -> str:
    """BB calls a 3-bet, wins at showdown, pays rake + jackpot."""
    return f"""Poker Hand #{hid}: Hold'em No Limit ($0.01/$0.02) - {dt}
Table 'RushAndCash1' 6-max Seat #1 is the button
Seat 1: p1 ($5 in chips)
Seat 2: p2 ($5 in chips)
Seat 3: Hero ($5 in chips)
Seat 4: p4 ($5 in chips)
Seat 5: p5 ($5 in chips)
Seat 6: p6 ($5 in chips)
p2: posts small blind $0.01
Hero: posts big blind $0.02
*** HOLE CARDS ***
Dealt to p1 
Dealt to p2 
Dealt to Hero [Qs Kc]
Dealt to p4 
Dealt to p5 
Dealt to p6 
p4: folds
p5: folds
p6: raises $0.03 to $0.05
p1: raises $0.09 to $0.14
p2: folds
Hero: calls $0.12
p6: folds
*** FLOP *** [4h 3s Kd]
Hero: checks
p1: bets $0.11
Hero: calls $0.11
*** TURN *** [4h 3s Kd] [5h]
Hero: checks
p1: checks
*** RIVER *** [4h 3s Kd 5h] [6h]
Hero: bets $0.19
p1: calls $0.19
Hero: shows [Qs Kc] (a pair of Kings)
p1: shows [Ks Js] (a pair of Kings)
*** SHOWDOWN ***
Hero collected $0.87 from pot
*** SUMMARY ***
Total pot $0.94 | Rake $0.04 | Jackpot $0.03 | Bingo $0 | Fortune $0 | Tax $0
Board [4h 3s Kd 5h 6h]
Seat 3: Hero (big blind) showed [Qs Kc] and won ($0.87)
"""


def hero_faces_3bet_folds(hid: str, dt: str) -> str:
    """BTN open, BB 3-bets, Hero folds."""
    return f"""Poker Hand #{hid}: Hold'em No Limit ($0.01/$0.02) - {dt}
Table 'RushAndCash1' 6-max Seat #1 is the button
Seat 1: Hero ($5 in chips)
Seat 2: p2 ($5 in chips)
Seat 3: p3 ($5 in chips)
Seat 4: p4 ($5 in chips)
Seat 5: p5 ($5 in chips)
Seat 6: p6 ($5 in chips)
p2: posts small blind $0.01
p3: posts big blind $0.02
*** HOLE CARDS ***
Dealt to Hero [Ah Kd]
Dealt to p2 
Dealt to p3 
Dealt to p4 
Dealt to p5 
Dealt to p6 
p4: folds
p5: folds
p6: folds
Hero: raises $0.04 to $0.06
p2: folds
p3: raises $0.16 to $0.22
Hero: folds
Uncalled bet ($0.16) returned to p3
*** SHOWDOWN ***
p3 collected $0.13 from pot
*** SUMMARY ***
Total pot $0.13 | Rake $0 | Jackpot $0 | Bingo $0 | Fortune $0 | Tax $0
Seat 1: Hero (button) folded before Flop
"""


def hero_btn_cbet(hid: str, dt: str) -> str:
    """BTN vs BB heads-up flop. Hero is IP and c-bets; BB folds."""
    return f"""Poker Hand #{hid}: Hold'em No Limit ($0.01/$0.02) - {dt}
Table 'RushAndCash1' 6-max Seat #1 is the button
Seat 1: Hero ($5 in chips)
Seat 2: p2 ($5 in chips)
Seat 3: p3 ($5 in chips)
Seat 4: p4 ($5 in chips)
Seat 5: p5 ($5 in chips)
Seat 6: p6 ($5 in chips)
p2: posts small blind $0.01
p3: posts big blind $0.02
*** HOLE CARDS ***
Dealt to Hero [Ah Kd]
Dealt to p2 
Dealt to p3 
Dealt to p4 
Dealt to p5 
Dealt to p6 
p4: folds
p5: folds
p6: folds
Hero: raises $0.04 to $0.06
p2: folds
p3: calls $0.04
*** FLOP *** [Qs Jh 2h]
p3: checks
Hero: bets $0.08
p3: folds
Uncalled bet ($0.08) returned to Hero
*** SHOWDOWN ***
Hero collected $0.13 from pot
*** SUMMARY ***
Total pot $0.13 | Rake $0 | Jackpot $0 | Bingo $0 | Fortune $0 | Tax $0
Board [Qs Jh 2h]
Seat 1: Hero (button) collected ($0.13)
"""


def parse(text: str):
    hand = parse_hand(text)
    assert hand is not None, "failed to parse hand"
    return hand
