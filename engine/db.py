"""SQLite storage for parsed GGPoker hands."""

from __future__ import annotations

from datetime import datetime
import re
import sqlite3
from pathlib import Path

from .parser import ParsedHand, PlayerFlags, starting_hand_key

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "poker.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS hands (
    id TEXT PRIMARY KEY,
    played_at TEXT NOT NULL,
    ts INTEGER NOT NULL,
    game TEXT,
    game_type TEXT,
    sb INTEGER,
    bb INTEGER,
    max_seats INTEGER,
    table_name TEXT,
    button INTEGER,
    hero_seat INTEGER,
    hero_pos TEXT,
    hero_cards TEXT,
    hand_key TEXT,
    board TEXT,
    players INTEGER,
    pot INTEGER,
    rake INTEGER,
    jackpot INTEGER,
    bingo INTEGER,
    fortune INTEGER,
    tax INTEGER,
    cash_drop INTEGER,
    hero_invested INTEGER,
    hero_collected INTEGER,
    hero_net INTEGER,
    run_it INTEGER,
    ev_cashout INTEGER,
    session_id INTEGER,
    source_file TEXT,
    raw TEXT,
    vpip INTEGER, pfr INTEGER,
    threebet INTEGER, threebet_opp INTEGER,
    fold_to_3bet INTEGER, fold_to_3bet_opp INTEGER, call_3bet INTEGER,
    fourbet INTEGER, fourbet_opp INTEGER,
    steal INTEGER, steal_opp INTEGER,
    fold_to_steal INTEGER, face_steal INTEGER,
    cbet_flop INTEGER, cbet_flop_opp INTEGER,
    fold_to_cbet INTEGER, face_cbet INTEGER, call_cbet INTEGER, raise_cbet INTEGER,
    wtsd INTEGER, saw_flop INTEGER, won_sd INTEGER, wwsf INTEGER,
    bets INTEGER, raises INTEGER, calls INTEGER, checks INTEGER,
    xr_flop INTEGER, xr_flop_opp INTEGER,
    squeeze INTEGER, squeeze_opp INTEGER,
    limp INTEGER, limp_opp INTEGER, allin INTEGER,
    fold_street TEXT
);

CREATE TABLE IF NOT EXISTS player_hands (
    hand_id TEXT NOT NULL,
    name TEXT NOT NULL,
    is_hero INTEGER,
    seat INTEGER,
    position TEXT,
    stack INTEGER,
    cards TEXT,
    invested INTEGER,
    collected INTEGER,
    net INTEGER,
    vpip INTEGER, pfr INTEGER,
    threebet INTEGER, threebet_opp INTEGER,
    fold_to_3bet INTEGER, fold_to_3bet_opp INTEGER, call_3bet INTEGER,
    fourbet INTEGER, fourbet_opp INTEGER,
    steal INTEGER, steal_opp INTEGER,
    fold_to_steal INTEGER, face_steal INTEGER,
    cbet_flop INTEGER, cbet_flop_opp INTEGER,
    fold_to_cbet INTEGER, face_cbet INTEGER, call_cbet INTEGER, raise_cbet INTEGER,
    wtsd INTEGER, saw_flop INTEGER, won_sd INTEGER, wwsf INTEGER,
    bets INTEGER, raises INTEGER, calls INTEGER, checks INTEGER,
    xr_flop INTEGER, xr_flop_opp INTEGER,
    squeeze INTEGER, squeeze_opp INTEGER,
    limp INTEGER, limp_opp INTEGER, allin INTEGER,
    PRIMARY KEY (hand_id, name)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    started_at TEXT,
    ended_at TEXT,
    start_ts INTEGER,
    end_ts INTEGER,
    hands INTEGER,
    net INTEGER,
    duration_sec INTEGER
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_hands_ts ON hands(ts);
CREATE INDEX IF NOT EXISTS idx_hands_pos ON hands(hero_pos);
CREATE INDEX IF NOT EXISTS idx_hands_session ON hands(session_id);
CREATE INDEX IF NOT EXISTS idx_hands_key ON hands(hand_key);
CREATE INDEX IF NOT EXISTS idx_ph_name ON player_hands(name);
"""

SOLVER_SCHEMA = """
CREATE TABLE IF NOT EXISTS solver_reviews (
    hand_id TEXT PRIMARY KEY,
    street TEXT,
    hero_role TEXT,
    hero_pos TEXT,
    hero_cards TEXT,
    hero_action TEXT,
    hero_action_type TEXT,
    gto_match TEXT,
    gto_freq REAL,
    gto_best TEXT,
    gto_best_freq REAL,
    ev_lost_cents INTEGER,
    pot INTEGER,
    board TEXT,
    in_range INTEGER,
    note TEXT,
    net INTEGER,
    updated_at TEXT,
    gto_mix TEXT
);

CREATE TABLE IF NOT EXISTS solver_cache (
    cache_key TEXT PRIMARY KEY,
    result_json TEXT NOT NULL,
    created_at TEXT
);
"""

FLAG_COLS = [
    "vpip", "pfr", "threebet", "threebet_opp", "fold_to_3bet", "fold_to_3bet_opp",
    "call_3bet", "fourbet", "fourbet_opp", "steal", "steal_opp", "fold_to_steal",
    "face_steal", "cbet_flop", "cbet_flop_opp", "fold_to_cbet", "face_cbet",
    "call_cbet", "raise_cbet", "wtsd", "saw_flop", "won_sd", "wwsf", "bets",
    "raises", "calls", "checks", "xr_flop", "xr_flop_opp", "squeeze",
    "squeeze_opp", "limp", "limp_opp", "allin",
]


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    own = conn is None
    conn = conn or connect()
    conn.executescript(SCHEMA)
    conn.executescript(SOLVER_SCHEMA)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(solver_reviews)").fetchall()}
    if "gto_mix" not in cols:
        conn.execute("ALTER TABLE solver_reviews ADD COLUMN gto_mix TEXT")
    conn.commit()
    if own:
        return conn
    return conn


def hand_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM hands").fetchone()
    return int(row["n"] if row else 0)


def session_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()
    return int(row["n"] if row else 0)


def _flag_tuple(fl: PlayerFlags) -> tuple:
    return tuple(int(getattr(fl, c)) for c in FLAG_COLS)


def insert_hands(conn: sqlite3.Connection, hands: list[ParsedHand]) -> dict:
    """Insert hands, skipping any whose GGPoker hand id is already stored."""
    inserted = 0
    skipped = 0
    errors = 0
    seen: set[str] = set()
    for hand in hands:
        if not hand.id or hand.id in seen:
            skipped += 1
            continue
        seen.add(hand.id)
        hero_seat = hand.hero_seat()
        hf = hand.hero_flags()
        cards = " ".join(hero_seat.cards) if hero_seat else ""
        try:
            cur = conn.execute(
                f"""
                INSERT OR IGNORE INTO hands (
                    id, played_at, ts, game, game_type, sb, bb, max_seats, table_name,
                    button, hero_seat, hero_pos, hero_cards, hand_key, board, players,
                    pot, rake, jackpot, bingo, fortune, tax, cash_drop, hero_invested,
                    hero_collected, hero_net, run_it, ev_cashout, session_id, source_file, raw,
                    {", ".join(FLAG_COLS)}, fold_street
                ) VALUES ({",".join(["?"] * (32 + len(FLAG_COLS)))})
                """,
                (
                    hand.id,
                    hand.played_at,
                    hand.ts,
                    hand.game,
                    hand.game_type,
                    hand.sb,
                    hand.bb,
                    hand.max_seats,
                    hand.table_name,
                    hand.button,
                    hero_seat.seat if hero_seat else 0,
                    hero_seat.position if hero_seat else "",
                    cards,
                    starting_hand_key(hero_seat.cards) if hero_seat else "",
                    " ".join(hand.board),
                    len(hand.seats),
                    hand.pot,
                    hand.rake,
                    hand.jackpot,
                    hand.bingo,
                    hand.fortune,
                    hand.tax,
                    hand.cash_drop,
                    hf.invested,
                    hf.collected,
                    hf.net,
                    hand.run_it,
                    hand.ev_cashout,
                    None,
                    hand.source_file,
                    hand.raw,
                    *_flag_tuple(hf),
                    hf.fold_street,
                ),
            )
            if cur.rowcount == 0:
                skipped += 1
                continue
            inserted += 1
            for seat in hand.seats:
                pf = hand.flags.get(seat.name) or PlayerFlags()
                conn.execute(
                    f"""
                    INSERT OR IGNORE INTO player_hands (
                        hand_id, name, is_hero, seat, position, stack, cards,
                        invested, collected, net, {", ".join(FLAG_COLS)}
                    ) VALUES ({",".join(["?"] * (10 + len(FLAG_COLS)))})
                    """,
                    (
                        hand.id,
                        seat.name,
                        1 if seat.is_hero else 0,
                        seat.seat,
                        seat.position,
                        seat.stack,
                        " ".join(seat.cards),
                        pf.invested,
                        pf.collected,
                        pf.net,
                        *_flag_tuple(pf),
                    ),
                )
        except sqlite3.Error:
            errors += 1
    conn.commit()
    return {"inserted": inserted, "skipped": skipped, "errors": errors}


def rebuild_sessions(conn: sqlite3.Connection, gap_sec: int = 20 * 60) -> int:
    conn.execute("DELETE FROM sessions")
    rows = conn.execute(
        "SELECT id, played_at, ts, hero_net FROM hands ORDER BY ts, id"
    ).fetchall()
    if not rows:
        conn.commit()
        return 0

    sessions = []
    cur = {
        "start_ts": rows[0]["ts"],
        "end_ts": rows[0]["ts"],
        "started_at": rows[0]["played_at"],
        "ended_at": rows[0]["played_at"],
        "hands": 0,
        "net": 0,
        "ids": [],
    }
    for row in rows:
        if cur["ids"] and row["ts"] - cur["end_ts"] > gap_sec:
            sessions.append(cur)
            cur = {
                "start_ts": row["ts"],
                "end_ts": row["ts"],
                "started_at": row["played_at"],
                "ended_at": row["played_at"],
                "hands": 0,
                "net": 0,
                "ids": [],
            }
        cur["end_ts"] = row["ts"]
        cur["ended_at"] = row["played_at"]
        cur["hands"] += 1
        cur["net"] += row["hero_net"]
        cur["ids"].append(row["id"])
    sessions.append(cur)

    for i, sess in enumerate(sessions, start=1):
        conn.execute(
            """
            INSERT INTO sessions (id, started_at, ended_at, start_ts, end_ts, hands, net, duration_sec)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                i,
                sess["started_at"],
                sess["ended_at"],
                sess["start_ts"],
                sess["end_ts"],
                sess["hands"],
                sess["net"],
                max(0, sess["end_ts"] - sess["start_ts"]),
            ),
        )
        conn.executemany(
            "UPDATE hands SET session_id = ? WHERE id = ?",
            [(i, hid) for hid in sess["ids"]],
        )
    conn.commit()
    return len(sessions)


def reset_db(conn) -> None:
    conn.executescript(SOLVER_SCHEMA)
    conn.execute("DELETE FROM player_hands")
    conn.execute("DELETE FROM hands")
    conn.execute("DELETE FROM sessions")
    conn.execute("DELETE FROM solver_reviews")
    conn.execute("DELETE FROM solver_cache")
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


_DAY_RE = re.compile(r"^(\d{4})[-/](\d{2})[-/](\d{2})")


def date_sql_bound(value: str | None, *, end_of_day: bool = False) -> str | None:
    """HTML date inputs are YYYY-MM-DD; GGPoker stores played_at as YYYY/MM/DD HH:MM:SS."""
    if not value:
        return None
    m = _DAY_RE.match(str(value).strip())
    if not m:
        return None
    y, mo, d = m.group(1), m.group(2), m.group(3)
    try:
        datetime.strptime(f"{y}-{mo}-{d}", "%Y-%m-%d")
    except ValueError:
        return None
    day = f"{y}/{mo}/{d}"
    return f"{day} 23:59:59" if end_of_day else f"{day} 00:00:00"


def filters_sql(args: dict) -> tuple[str, list]:
    clauses = ["1=1"]
    params: list = []
    game = args.get("game")
    if game and game not in ("all", ""):
        clauses.append("game_type = ?")
        params.append(game)
    pos = args.get("position")
    if pos and pos not in ("all", ""):
        clauses.append("hero_pos = ?")
        params.append(pos)
    date_from = date_sql_bound(args.get("from"))
    if date_from:
        clauses.append("played_at >= ?")
        params.append(date_from)
    date_to = date_sql_bound(args.get("to"), end_of_day=True)
    if date_to:
        clauses.append("played_at <= ?")
        params.append(date_to)
    result = args.get("result")
    if result == "won":
        clauses.append("hero_net > 0")
    elif result == "lost":
        clauses.append("hero_net < 0")
    elif result == "even":
        clauses.append("hero_net = 0")
    if args.get("saw_flop") == "1":
        clauses.append("saw_flop = 1")
    if args.get("wtsd") == "1":
        clauses.append("wtsd = 1")
    if args.get("vpip") == "1":
        clauses.append("vpip = 1")
    if args.get("pfr") == "1":
        clauses.append("pfr = 1")
    hand_key = args.get("hand")
    if hand_key:
        clauses.append("hand_key = ?")
        params.append(hand_key)
    q = args.get("q")
    if q:
        clauses.append("(id LIKE ? OR hero_cards LIKE ? OR board LIKE ? OR raw LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like, like])
    return " AND ".join(clauses), params
