"""Parse GGPoker / GGNetwork cash hand histories (PokerStars-style text)."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
import re
from typing import Iterable

MONEY_RE = re.compile(r"\$([0-9]+(?:\.[0-9]+)?)")
CARDS_RE = re.compile(r"\[([2-9TJQKA][cdhs](?:\s+[2-9TJQKA][cdhs])*)\]")
HEADER_RE = re.compile(
    r"Poker Hand #(?P<id>\S+): (?P<game>.+?) "
    r"\(\$(?P<sb>[0-9.]+)/\$(?P<bb>[0-9.]+)\) - "
    r"(?P<dt>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})"
)
TABLE_RE = re.compile(
    r"Table '(?P<table>[^']+)' (?P<max>\d+)-max Seat #(?P<button>\d+) is the button"
)
SEAT_RE = re.compile(
    r"Seat (?P<seat>\d+): (?P<name>.+?) \(\$(?P<stack>[0-9.]+) in chips\)"
)
DEALT_RE = re.compile(r"^Dealt to (?P<name>.+?)(?: \[(?P<cards>[^\]]*)\])?\s*$")
UNCALLED_RE = re.compile(
    r"^Uncalled bet \(\$(?P<amt>[0-9.]+)\) returned to (?P<name>.+)$"
)
COLLECT_RE = re.compile(
    r"^(?P<name>.+?) collected \$(?P<amt>[0-9.]+) from (?:pot|side pot(?:-\d+)?|main pot)$"
)
POT_RE = re.compile(
    r"Total pot \$(?P<pot>[0-9.]+) \| Rake \$(?P<rake>[0-9.]+)"
    r"(?: \| Jackpot \$(?P<jackpot>[0-9.]+))?"
    r"(?: \| Bingo \$(?P<bingo>[0-9.]+))?"
    r"(?: \| Fortune \$(?P<fortune>[0-9.]+))?"
    r"(?: \| Tax \$(?P<tax>[0-9.]+))?"
)
CASH_DROP_RE = re.compile(r"Cash Drop to Pot : total \$([0-9.]+)")
CASHOUT_RECV_RE = re.compile(r"^(?P<name>.+?): Receives Cashout \(\$(?P<amt>[0-9.]+)\)")
CASHOUT_RISK_RE = re.compile(r"^(?P<name>.+?): Pays Cashout Risk \(\$(?P<amt>[0-9.]+)\)")
ACTION_RE = re.compile(
    r"^(?P<name>.+?): (?P<verb>folds|checks|calls|bets|raises|shows|mucks|posts|doesn't show hand)"
    r"(?P<rest>.*)$"
)
STREET_RE = re.compile(r"^\*\*\* (?P<label>.+?) \*\*\*(?P<rest>.*)$")
BOARD_SUMMARY_RE = re.compile(r"^(?:FIRST |SECOND |THIRD )?Board \[(?P<cards>[^\]]+)\]")

RANKS = "AKQJT98765432"
STEAL_POS = {"CO", "BTN", "SB"}
POSTFLOP_AF_STREETS = {"flop", "turn", "river"}

POSITIONS = {
    2: ["SB", "BB"],
    3: ["BTN", "SB", "BB"],
    4: ["BTN", "SB", "BB", "CO"],
    5: ["BTN", "SB", "BB", "UTG", "CO"],
    6: ["BTN", "SB", "BB", "UTG", "HJ", "CO"],
    7: ["BTN", "SB", "BB", "UTG", "UTG+1", "HJ", "CO"],
    8: ["BTN", "SB", "BB", "UTG", "UTG+1", "MP", "HJ", "CO"],
    9: ["BTN", "SB", "BB", "UTG", "UTG+1", "MP", "LJ", "HJ", "CO"],
}

STREET_MAP = {
    "HOLE CARDS": "preflop",
    "FLOP": "flop",
    "TURN": "turn",
    "RIVER": "river",
    "FIRST FLOP": "flop",
    "FIRST TURN": "turn",
    "FIRST RIVER": "river",
    "SECOND FLOP": "flop2",
    "SECOND TURN": "turn2",
    "SECOND RIVER": "river2",
    "THIRD FLOP": "flop3",
    "THIRD TURN": "turn3",
    "THIRD RIVER": "river3",
    "SHOWDOWN": "showdown",
    "FIRST SHOWDOWN": "showdown",
    "SECOND SHOWDOWN": "showdown2",
    "THIRD SHOWDOWN": "showdown3",
    "SUMMARY": "summary",
}


def money_cents(text: str | None) -> int:
    if not text:
        return 0
    m = MONEY_RE.search(text)
    if not m:
        return 0
    return round(float(m.group(1)) * 100)


def parse_cards(text: str | None) -> list[str]:
    if not text:
        return []
    return [c for c in text.strip().split() if c]


def starting_hand_key(cards: list[str]) -> str:
    if len(cards) < 2:
        return ""
    a, b = cards[0], cards[1]
    r1, s1 = a[0], a[1]
    r2, s2 = b[0], b[1]
    if RANKS.index(r1) > RANKS.index(r2):
        r1, s1, r2, s2 = r2, s2, r1, s1
    if r1 == r2:
        return r1 + r2
    return r1 + r2 + ("s" if s1 == s2 else "o")


def assign_positions(seats: list["Seat"], button: int) -> None:
    ordered = sorted(seats, key=lambda s: s.seat)
    n = len(ordered)
    if n < 2:
        return
    labels = POSITIONS.get(n)
    if not labels:
        labels = ["BTN", "SB", "BB"] + [f"EP{i}" for i in range(n - 3)]
        labels = labels[:n]
    btn_idx = 0
    for i, seat in enumerate(ordered):
        if seat.seat == button:
            btn_idx = i
            break
    for i, seat in enumerate(ordered):
        seat.position = labels[(i - btn_idx) % n]


@dataclass
class Seat:
    seat: int
    name: str
    stack: int
    position: str = ""
    cards: list[str] = field(default_factory=list)
    is_hero: bool = False


@dataclass
class Action:
    street: str
    player: str
    type: str
    amount: int = 0
    to_amount: int = 0
    allin: bool = False
    cards: list[str] = field(default_factory=list)
    text: str = ""


@dataclass
class PlayerFlags:
    vpip: int = 0
    pfr: int = 0
    threebet: int = 0
    threebet_opp: int = 0
    fold_to_3bet: int = 0
    fold_to_3bet_opp: int = 0
    call_3bet: int = 0
    fourbet: int = 0
    fourbet_opp: int = 0
    steal: int = 0
    steal_opp: int = 0
    fold_to_steal: int = 0
    face_steal: int = 0
    cbet_flop: int = 0
    cbet_flop_opp: int = 0
    fold_to_cbet: int = 0
    face_cbet: int = 0
    call_cbet: int = 0
    raise_cbet: int = 0
    wtsd: int = 0
    saw_flop: int = 0
    won_sd: int = 0
    wwsf: int = 0
    bets: int = 0
    raises: int = 0
    calls: int = 0
    checks: int = 0
    xr_flop: int = 0
    xr_flop_opp: int = 0
    squeeze: int = 0
    squeeze_opp: int = 0
    limp: int = 0
    limp_opp: int = 0
    allin: int = 0
    fold_street: str = ""
    invested: int = 0
    collected: int = 0
    cashout_risk: int = 0
    cashout_recv: int = 0
    net: int = 0


@dataclass
class ParsedHand:
    id: str
    played_at: str
    ts: int
    game: str
    game_type: str
    sb: int
    bb: int
    max_seats: int
    table_name: str
    button: int
    seats: list[Seat]
    actions: list[Action]
    board: list[str]
    board2: list[str]
    board3: list[str]
    pot: int
    rake: int
    jackpot: int
    bingo: int
    fortune: int
    tax: int
    cash_drop: int
    run_it: int
    ev_cashout: int
    hero: str
    flags: dict[str, PlayerFlags]
    source_file: str
    raw: str

    def hero_flags(self) -> PlayerFlags:
        return self.flags.get(self.hero) or PlayerFlags()

    def hero_seat(self) -> Seat | None:
        for seat in self.seats:
            if seat.is_hero:
                return seat
        return None

    def to_replay(self) -> dict:
        return {
            "id": self.id,
            "played_at": self.played_at,
            "game": self.game,
            "sb": self.sb,
            "bb": self.bb,
            "table": self.table_name,
            "button": self.button,
            "pot": self.pot,
            "rake": self.rake,
            "board": self.board,
            "board2": self.board2,
            "board3": self.board3,
            "run_it": self.run_it,
            "seats": [asdict(s) for s in self.seats],
            "actions": [asdict(a) for a in self.actions],
        }


def split_hands(text: str) -> list[str]:
    chunks = re.split(r"(?=Poker Hand #)", text)
    return [c.strip() for c in chunks if c.strip().startswith("Poker Hand #")]


def parse_file(text: str, source_file: str = "") -> list[ParsedHand]:
    return [h for block in split_hands(text) if (h := parse_hand(block, source_file))]


def parse_hand(text: str, source_file: str = "") -> ParsedHand | None:
    lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip() or True]
    header = None
    table = None
    for ln in lines:
        s = ln.strip()
        if header is None:
            header = HEADER_RE.match(s)
        if table is None:
            table = TABLE_RE.match(s)
        if header and table:
            break
    if not header or not table:
        return None

    game = header.group("game")
    if "Omaha" in game:
        game_type = "PLO"
    elif "Hold'em" in game or "Holdem" in game:
        game_type = "NLHE"
    else:
        game_type = game
    played_at = header.group("dt")
    try:
        ts = int(datetime.strptime(played_at, "%Y/%m/%d %H:%M:%S").timestamp())
    except ValueError:
        ts = 0

    seats: list[Seat] = []
    by_name: dict[str, Seat] = {}
    actions: list[Action] = []
    board: list[str] = []
    board2: list[str] = []
    board3: list[str] = []
    pot = rake = jackpot = bingo = fortune = tax = cash_drop = 0
    run_it = 1
    ev_cashout = 0
    street = "preflop"
    in_summary = False

    flags: dict[str, PlayerFlags] = {}
    invested: dict[str, int] = {}
    street_put: dict[str, int] = {}
    folded: set[str] = set()
    remaining: set[str] = set()
    checked_flop: set[str] = set()
    flop_bet = False
    flop_cbet = False
    faced_flop_bet: set[str] = set()
    pfa: str | None = None
    pf_raises = 0
    pf_callers_after_raise = 0
    last_raiser: str | None = None
    anyone_vpip = False
    steal_happened = False
    shown: set[str] = set()

    def ensure(name: str) -> PlayerFlags:
        if name not in flags:
            flags[name] = PlayerFlags()
        return flags[name]

    def add_invest(name: str, cents: int) -> None:
        invested[name] = invested.get(name, 0) + cents
        street_put[name] = street_put.get(name, 0) + cents

    for raw_line in lines[1:]:
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("Hand was run two times"):
            run_it = 2
            continue
        if line.startswith("Hand was run three times"):
            run_it = 3
            continue

        drop = CASH_DROP_RE.search(line)
        if drop:
            cash_drop = round(float(drop.group(1)) * 100)
            continue

        sm = STREET_RE.match(line)
        if sm:
            label = sm.group("label")
            street = STREET_MAP.get(label, label.lower())
            rest = sm.group("rest") or ""
            cards_found = CARDS_RE.findall(rest)
            if label == "HOLE CARDS" and seats:
                assign_positions(seats, int(table.group("button")))
            if label in ("FLOP", "FIRST FLOP") and cards_found:
                board = parse_cards(cards_found[0])
                street_put = {n: 0 for n in remaining}
                for name in list(remaining):
                    ensure(name).saw_flop = 1
            elif label in ("TURN", "FIRST TURN") and cards_found:
                extra = parse_cards(cards_found[-1])
                if extra:
                    if len(board) == 3:
                        board.append(extra[0])
                    street_put = {n: 0 for n in remaining}
            elif label in ("RIVER", "FIRST RIVER") and cards_found:
                extra = parse_cards(cards_found[-1])
                if extra:
                    if len(board) == 4:
                        board.append(extra[0])
                    street_put = {n: 0 for n in remaining}
            elif "SECOND" in label and cards_found:
                extra = parse_cards(" ".join(cards_found))
                for c in extra:
                    if c not in board2:
                        board2.append(c)
            elif "THIRD" in label and cards_found:
                extra = parse_cards(" ".join(cards_found))
                for c in extra:
                    if c not in board3:
                        board3.append(c)
            if street == "summary":
                in_summary = True
            continue

        if in_summary:
            pm = POT_RE.search(line)
            if pm:
                pot = round(float(pm.group("pot")) * 100)
                rake = round(float(pm.group("rake")) * 100)
                jackpot = round(float(pm.group("jackpot") or 0) * 100)
                bingo = round(float(pm.group("bingo") or 0) * 100)
                fortune = round(float(pm.group("fortune") or 0) * 100)
                tax = round(float(pm.group("tax") or 0) * 100)
                continue
            bm = BOARD_SUMMARY_RE.match(line)
            if bm:
                cards = parse_cards(bm.group("cards"))
                if line.startswith("SECOND"):
                    board2 = cards if len(cards) >= len(board2) else board2 + [c for c in cards if c not in board2]
                elif line.startswith("THIRD"):
                    board3 = cards
                elif not board:
                    board = cards
                continue
            continue

        seat_m = SEAT_RE.match(line)
        if seat_m and street == "preflop" and not actions:
            seat = Seat(
                seat=int(seat_m.group("seat")),
                name=seat_m.group("name"),
                stack=round(float(seat_m.group("stack")) * 100),
                is_hero=seat_m.group("name") == "Hero",
            )
            seats.append(seat)
            by_name[seat.name] = seat
            remaining.add(seat.name)
            ensure(seat.name)
            invested.setdefault(seat.name, 0)
            continue

        dealt = DEALT_RE.match(line)
        if dealt:
            name = dealt.group("name").strip()
            cards = parse_cards(dealt.group("cards"))
            if name in by_name and cards:
                by_name[name].cards = cards
            continue

        um = UNCALLED_RE.match(line)
        if um:
            name = um.group("name")
            amt = round(float(um.group("amt")) * 100)
            invested[name] = max(0, invested.get(name, 0) - amt)
            street_put[name] = max(0, street_put.get(name, 0) - amt)
            actions.append(Action(street, name, "uncalled", amt, text=line))
            continue

        cm = COLLECT_RE.match(line)
        if cm:
            name = cm.group("name")
            amt = round(float(cm.group("amt")) * 100)
            ensure(name).collected += amt
            actions.append(Action(street, name, "collect", amt, text=line))
            continue

        crm = CASHOUT_RECV_RE.match(line)
        if crm:
            name = crm.group("name")
            amt = round(float(crm.group("amt")) * 100)
            ensure(name).cashout_recv += amt
            ev_cashout = 1
            actions.append(Action(street, name, "cashout_recv", amt, text=line))
            continue

        ckm = CASHOUT_RISK_RE.match(line)
        if ckm:
            name = ckm.group("name")
            amt = round(float(ckm.group("amt")) * 100)
            ensure(name).cashout_risk += amt
            ev_cashout = 1
            actions.append(Action(street, name, "cashout_risk", amt, text=line))
            continue

        if ": Chooses to EV Cashout" in line:
            ev_cashout = 1
            name = line.split(":", 1)[0]
            actions.append(Action(street, name, "ev_cashout", text=line))
            continue

        am = ACTION_RE.match(line)
        if not am:
            continue

        name = am.group("name")
        verb = am.group("verb")
        rest = am.group("rest") or ""
        allin = "all-in" in rest
        fl = ensure(name)

        if verb == "posts":
            amt = money_cents(rest)
            add_invest(name, amt)
            kind = "sb" if "small" in rest else "bb" if "big" in rest else "post"
            actions.append(Action("preflop", name, kind, amt, allin=allin, text=line))
            continue

        if verb == "shows":
            cards = []
            found = CARDS_RE.search(rest)
            if found:
                cards = parse_cards(found.group(1))
                if name in by_name and not by_name[name].cards:
                    by_name[name].cards = cards
            shown.add(name)
            actions.append(Action(street, name, "show", cards=cards, text=line))
            continue

        if verb in ("mucks", "doesn't show hand"):
            actions.append(Action(street, name, "muck", text=line))
            continue

        if verb == "folds":
            folded.add(name)
            remaining.discard(name)
            fl.fold_street = street
            if street == "flop" and flop_bet:
                if flop_cbet:
                    fl.face_cbet = 1
                    fl.fold_to_cbet = 1
                if name in checked_flop:
                    fl.xr_flop_opp = 1
            actions.append(Action(street, name, "fold", text=line))
            continue

        if verb == "checks":
            if street in POSTFLOP_AF_STREETS:
                fl.checks += 1
            if street == "flop":
                checked_flop.add(name)
                if pfa == name and not flop_bet:
                    fl.cbet_flop_opp = 1
            actions.append(Action(street, name, "check", text=line))
            continue

        if verb == "calls":
            amt = money_cents(rest)
            add_invest(name, amt)
            if allin:
                fl.allin = 1
            if street == "preflop":
                fl.vpip = 1
                anyone_vpip = True
                if pf_raises == 0:
                    fl.limp = 1
                else:
                    pf_callers_after_raise += 1
                    if pf_raises >= 2:
                        fl.call_3bet = 1
            elif street in POSTFLOP_AF_STREETS:
                fl.calls += 1
            if street == "flop" and flop_bet:
                faced_flop_bet.add(name)
                if flop_cbet:
                    fl.face_cbet = 1
                    fl.call_cbet = 1
                if name in checked_flop:
                    fl.xr_flop_opp = 1
            actions.append(Action(street, name, "call", amt, allin=allin, text=line))
            continue

        if verb == "bets":
            amt = money_cents(rest)
            add_invest(name, amt)
            if allin:
                fl.allin = 1
            if street in POSTFLOP_AF_STREETS:
                fl.bets += 1
            if street == "flop":
                if pfa == name and not flop_bet:
                    fl.cbet_flop_opp = 1
                    fl.cbet_flop = 1
                    flop_cbet = True
                flop_bet = True
                for other in remaining:
                    if other != name and other in checked_flop:
                        ensure(other).xr_flop_opp = 1
            actions.append(Action(street, name, "bet", amt, allin=allin, text=line))
            continue

        if verb == "raises":
            to_amt = 0
            m2 = re.search(r"\$([0-9.]+) to \$([0-9.]+)", rest)
            if m2:
                to_amt = round(float(m2.group(2)) * 100)
                already = street_put.get(name, 0)
                inc = max(0, to_amt - already)
            else:
                inc = money_cents(rest)
            add_invest(name, inc)
            if allin:
                fl.allin = 1
            if street == "preflop":
                pf_raises += 1
                last_raiser = name
                pfa = name
                pf_callers_after_raise = 0
            elif street in POSTFLOP_AF_STREETS:
                fl.raises += 1
            if street == "flop":
                if pfa == name and not flop_bet:
                    fl.cbet_flop_opp = 1
                    fl.cbet_flop = 1
                    flop_cbet = True
                if flop_cbet and flop_bet and name != pfa:
                    fl.face_cbet = 1
                    fl.raise_cbet = 1
                if name in checked_flop:
                    fl.xr_flop = 1
                flop_bet = True
            actions.append(
                Action(street, name, "raise", inc, to_amount=to_amt, allin=allin, text=line)
            )
            continue

    if seats and not any(s.position for s in seats):
        assign_positions(seats, int(table.group("button")))

    hero = "Hero"
    still = {s.name for s in seats if s.name not in folded}
    went_sd = len(still) >= 2
    for name, fl in flags.items():
        fl.invested = invested.get(name, 0)
        if fl.cashout_recv and not fl.collected:
            fl.collected += fl.cashout_recv
        fl.net = fl.collected - fl.invested - fl.cashout_risk
        if fl.saw_flop:
            if went_sd and name in still:
                fl.wtsd = 1
            if fl.collected > 0:
                fl.wwsf = 1
            if fl.wtsd and fl.collected > 0:
                fl.won_sd = 1

    # Second pass for steal_opp using positions now that they exist.
    _apply_preflop_with_positions(seats, actions, flags)

    for seat in seats:
        seat.position = seat.position or ""

    return ParsedHand(
        id=header.group("id"),
        played_at=played_at,
        ts=ts,
        game=game,
        game_type=game_type,
        sb=round(float(header.group("sb")) * 100),
        bb=round(float(header.group("bb")) * 100),
        max_seats=int(table.group("max")),
        table_name=table.group("table"),
        button=int(table.group("button")),
        seats=seats,
        actions=actions,
        board=board,
        board2=board2,
        board3=board3,
        pot=pot,
        rake=rake,
        jackpot=jackpot,
        bingo=bingo,
        fortune=fortune,
        tax=tax,
        cash_drop=cash_drop,
        run_it=run_it,
        ev_cashout=ev_cashout,
        hero=hero,
        flags=flags,
        source_file=source_file,
        raw=text.strip() + "\n",
    )


def _apply_preflop_with_positions(
    seats: list[Seat], actions: list[Action], flags: dict[str, PlayerFlags]
) -> None:
    """Recompute preflop opportunity flags now that positions are assigned."""
    pos = {s.name: s.position for s in seats}
    for fl in flags.values():
        fl.steal = 0
        fl.steal_opp = 0
        fl.threebet = 0
        fl.threebet_opp = 0
        fl.fold_to_3bet = 0
        fl.fold_to_3bet_opp = 0
        fl.call_3bet = 0
        fl.fourbet = 0
        fl.fourbet_opp = 0
        fl.squeeze = 0
        fl.squeeze_opp = 0
        fl.limp = 0
        fl.limp_opp = 0
        fl.fold_to_steal = 0
        fl.face_steal = 0
        fl.vpip = 0
        fl.pfr = 0

    pf_raises = 0
    callers = 0
    last_raiser = None
    anyone_vpip = False
    steal_happened = False

    for act in actions:
        if act.street != "preflop":
            continue
        if act.type in ("sb", "bb", "post", "uncalled", "collect", "show", "muck"):
            continue
        name = act.player
        fl = flags.setdefault(name, PlayerFlags())
        p = pos.get(name, "")
        verb = {
            "fold": "folds",
            "check": "checks",
            "call": "calls",
            "raise": "raises",
            "bet": "bets",
        }.get(act.type, act.type)

        if verb in ("folds", "checks", "calls", "raises"):
            if pf_raises == 0 and verb != "checks":
                fl.limp_opp = 1
                if p in STEAL_POS and not anyone_vpip:
                    fl.steal_opp = 1
            if pf_raises == 1:
                fl.threebet_opp = 1
                if callers >= 1:
                    fl.squeeze_opp = 1
                if steal_happened and p in {"BB", "SB"}:
                    fl.face_steal = 1
            if pf_raises >= 2:
                fl.fourbet_opp = 1
                if last_raiser == name:
                    fl.fold_to_3bet_opp = 1

        if verb == "folds":
            if fl.fold_to_3bet_opp:
                fl.fold_to_3bet = 1
            if pf_raises == 1 and steal_happened and p in {"BB", "SB"}:
                fl.fold_to_steal = 1
            continue
        if verb == "checks":
            continue
        if verb == "calls":
            fl.vpip = 1
            anyone_vpip = True
            if pf_raises == 0:
                fl.limp = 1
            else:
                callers += 1
                if pf_raises >= 2:
                    fl.call_3bet = 1
            continue
        if verb == "raises":
            was_unopened = pf_raises == 0
            fl.vpip = 1
            fl.pfr = 1
            if was_unopened and p in STEAL_POS and not anyone_vpip:
                fl.steal_opp = 1
                fl.steal = 1
                steal_happened = True
            if pf_raises == 1:
                fl.threebet = 1
                if callers >= 1:
                    fl.squeeze = 1
                if last_raiser:
                    flags.setdefault(last_raiser, PlayerFlags()).fold_to_3bet_opp = 1
            if pf_raises >= 2:
                fl.fourbet = 1
            anyone_vpip = True
            pf_raises += 1
            last_raiser = name
            callers = 0


def iter_parse_files(files: Iterable[tuple[str, str]]) -> Iterable[ParsedHand]:
    """Yield parsed hands from (filename, text) pairs."""
    seen: set[str] = set()
    for source, text in files:
        for hand in parse_file(text, source):
            if hand.id in seen:
                continue
            seen.add(hand.id)
            yield hand
