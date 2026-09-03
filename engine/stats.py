"""HUD stats, reports, and leak finder."""

from __future__ import annotations

import sqlite3

from .db import filters_sql

POS_ORDER = ["UTG", "HJ", "CO", "BTN", "SB", "BB"]

BENCHMARKS = {
    "vpip": {
        "low": 22, "high": 28, "label": "VPIP", "unit": "%",
        "low_note": "too tight — missing playable spots",
        "high_note": "too loose — playing too many hands",
        "ok_note": "typical 6-max cash range",
    },
    "pfr": {
        "low": 18, "high": 24, "label": "PFR", "unit": "%",
        "low_note": "not raising enough when you enter pots",
        "high_note": "opening too wide",
        "ok_note": "should sit a few points under VPIP",
    },
    "gap": {
        "low": 3, "high": 8, "label": "VPIP-PFR gap", "unit": "pp",
        "low_note": "almost never calling — very raise-or-fold",
        "high_note": "too much calling",
        "ok_note": "calling frequency is in line",
    },
    "threebet": {
        "low": 7, "high": 11, "label": "3-bet", "unit": "%",
        "low_note": "3-bet range is too small",
        "high_note": "3-betting too wide",
        "ok_note": "6-max needs a real 3-bet range",
    },
    "fold_to_3bet": {
        "low": 45, "high": 62, "label": "Fold to 3-bet", "unit": "%",
        "low_note": "calling or 4-betting too often vs 3-bets",
        "high_note": "overfolding to 3-bets",
        "ok_note": "defense vs 3-bets is in range",
    },
    "steal": {
        "low": 32, "high": 45, "label": "Steal", "unit": "%",
        "low_note": "not opening enough from CO/BTN/SB",
        "high_note": "opening too wide when folded to",
        "ok_note": "steal frequency from late position is in range",
    },
    "fold_to_steal": {
        "low": 68, "high": 82, "label": "Fold BB vs steal", "unit": "%",
        "low_note": "defending blinds too wide",
        "high_note": "folding too much vs steals — defend or 3-bet more",
        "ok_note": "blind defense vs steals is in range",
    },
    "cbet_flop": {
        "low": 50, "high": 70, "label": "C-bet flop", "unit": "%",
        "low_note": "giving up too often",
        "high_note": "barreling too thin",
        "ok_note": "flop c-bet frequency is in range",
    },
    "fold_to_cbet": {
        "low": 38, "high": 55, "label": "Fold to flop c-bet", "unit": "%",
        "low_note": "calling station — folding too little",
        "high_note": "overfolding to flop c-bets",
        "ok_note": "flop defense vs c-bets is in range",
    },
    "wtsd": {
        "low": 24, "high": 32, "label": "WTSD", "unit": "%",
        "low_note": "giving up too much after seeing a flop",
        "high_note": "going to showdown too often",
        "ok_note": "showdown frequency after flop is in range",
    },
    "wsd": {
        "low": 50, "high": 56, "label": "W$SD", "unit": "%",
        "low_note": "showing down too weak",
        "high_note": "winning showdowns at a high clip",
        "ok_note": "showdown win rate is in range",
    },
    "af": {
        "low": 2.2, "high": 3.6, "label": "Aggression factor", "unit": "x",
        "low_note": "too passive postflop",
        "high_note": "too aggressive postflop",
        "ok_note": "postflop (bets+raises)/calls is in range",
    },
}


def _pct(num, den) -> float | None:
    if not den:
        return None
    return round(100.0 * num / den, 2)


def _div(num, den) -> float | None:
    if not den:
        return None
    return round(num / den, 2)


def dollars(cents: int | None) -> float:
    return round((cents or 0) / 100.0, 2)


def hero_rake_paid_cents(row) -> int:
    """Fees taken from pots Hero actually collected — the money missing due to rake."""
    fees = (
        (row["rake"] or 0)
        + (row["jackpot"] or 0)
        + (row["bingo"] or 0)
        + (row["fortune"] or 0)
        + (row["tax"] or 0)
    )
    collected = row["hero_collected"] or 0
    if collected <= 0 or fees <= 0:
        return 0
    distributed = (row["pot"] or 0) - fees
    if distributed > 0:
        return round(fees * collected / distributed)
    return fees


def hud_from_row(row: sqlite3.Row | dict, hands_key: str = "hands") -> dict:
    def g(key, default=0):
        try:
            return row[key]
        except (KeyError, IndexError):
            return default

    hands = g(hands_key) or 0
    net = g("net") or 0
    bb = g("bb_sum") or g("bb") or 0
    avg_bb = (bb / hands) if hands else 0
    bb_won = (net / avg_bb) if avg_bb else 0
    bets = g("bets") or 0
    raises = g("raises") or 0
    calls = g("calls") or 0
    return {
        "hands": hands,
        "net": dollars(net),
        "net_cents": net,
        "bb_won": round(bb_won, 2) if avg_bb else 0,
        "bb100": round(100.0 * net / bb, 2) if bb else 0,
        "vpip": _pct(g("vpip"), hands),
        "pfr": _pct(g("pfr"), hands),
        "threebet": _pct(g("threebet"), g("threebet_opp")),
        "fold_to_3bet": _pct(g("fold_to_3bet"), g("fold_to_3bet_opp")),
        "call_3bet": _pct(g("call_3bet"), g("fold_to_3bet_opp")),
        "fourbet": _pct(g("fourbet"), g("fourbet_opp")),
        "steal": _pct(g("steal"), g("steal_opp")),
        "fold_to_steal": _pct(g("fold_to_steal"), g("face_steal")),
        "cbet_flop": _pct(g("cbet_flop"), g("cbet_flop_opp")),
        "fold_to_cbet": _pct(g("fold_to_cbet"), g("face_cbet")),
        "wtsd": _pct(g("wtsd"), g("saw_flop")),
        "wsd": _pct(g("won_sd"), g("wtsd")),
        "wwsf": _pct(g("wwsf"), g("saw_flop")),
        "limp": _pct(g("limp"), g("limp_opp")),
        "squeeze": _pct(g("squeeze"), g("squeeze_opp")),
        "xr_flop": _pct(g("xr_flop"), g("xr_flop_opp")),
        "af": _div(bets + raises, calls) if calls else (bets + raises if (bets + raises) else None),
        "saw_flop": _pct(g("saw_flop"), hands),
        "allin": g("allin") or 0,
        "rake": dollars(g("rake")),
        "rake_paid": dollars(g("rake_paid")),
        "pot": dollars(g("pot")),
    }


AGG_SQL = """
SELECT
  COUNT(*) AS hands,
  SUM(hero_net) AS net,
  SUM(bb) AS bb_sum,
  SUM(vpip) AS vpip,
  SUM(pfr) AS pfr,
  SUM(threebet) AS threebet,
  SUM(threebet_opp) AS threebet_opp,
  SUM(fold_to_3bet) AS fold_to_3bet,
  SUM(fold_to_3bet_opp) AS fold_to_3bet_opp,
  SUM(call_3bet) AS call_3bet,
  SUM(fourbet) AS fourbet,
  SUM(fourbet_opp) AS fourbet_opp,
  SUM(steal) AS steal,
  SUM(steal_opp) AS steal_opp,
  SUM(fold_to_steal) AS fold_to_steal,
  SUM(face_steal) AS face_steal,
  SUM(cbet_flop) AS cbet_flop,
  SUM(cbet_flop_opp) AS cbet_flop_opp,
  SUM(fold_to_cbet) AS fold_to_cbet,
  SUM(face_cbet) AS face_cbet,
  SUM(wtsd) AS wtsd,
  SUM(saw_flop) AS saw_flop,
  SUM(won_sd) AS won_sd,
  SUM(wwsf) AS wwsf,
  SUM(bets) AS bets,
  SUM(raises) AS raises,
  SUM(calls) AS calls,
  SUM(checks) AS checks,
  SUM(xr_flop) AS xr_flop,
  SUM(xr_flop_opp) AS xr_flop_opp,
  SUM(squeeze) AS squeeze,
  SUM(squeeze_opp) AS squeeze_opp,
  SUM(limp) AS limp,
  SUM(limp_opp) AS limp_opp,
  SUM(allin) AS allin,
  SUM(rake) AS rake,
  SUM(pot) AS pot,
  SUM(
    CASE
      WHEN hero_collected > 0 AND (COALESCE(rake,0)+COALESCE(jackpot,0)+COALESCE(bingo,0)+COALESCE(fortune,0)+COALESCE(tax,0)) > 0
      THEN CASE
        WHEN (pot - (COALESCE(rake,0)+COALESCE(jackpot,0)+COALESCE(bingo,0)+COALESCE(fortune,0)+COALESCE(tax,0))) > 0
        THEN ROUND(
          1.0 * (COALESCE(rake,0)+COALESCE(jackpot,0)+COALESCE(bingo,0)+COALESCE(fortune,0)+COALESCE(tax,0))
          * hero_collected
          / (pot - (COALESCE(rake,0)+COALESCE(jackpot,0)+COALESCE(bingo,0)+COALESCE(fortune,0)+COALESCE(tax,0)))
        )
        ELSE COALESCE(rake,0)+COALESCE(jackpot,0)+COALESCE(bingo,0)+COALESCE(fortune,0)+COALESCE(tax,0)
      END
      ELSE 0
    END
  ) AS rake_paid,
  MIN(played_at) AS first_hand,
  MAX(played_at) AS last_hand,
  SUM(CASE WHEN hero_net > 0 THEN 1 ELSE 0 END) AS won_hands,
  SUM(CASE WHEN hero_net < 0 THEN 1 ELSE 0 END) AS lost_hands
FROM hands
WHERE {where}
"""


def summary(conn: sqlite3.Connection, args: dict) -> dict:
    where, params = filters_sql(args)
    row = conn.execute(AGG_SQL.format(where=where), params).fetchone()
    hud = hud_from_row(row)
    paid = 0
    for hand in conn.execute(
        f"""
        SELECT hero_collected, pot, rake, jackpot, bingo, fortune, tax
        FROM hands WHERE {where}
        """,
        params,
    ):
        paid += hero_rake_paid_cents(hand)
    hud["rake_paid"] = dollars(paid)
    bb = row["bb_sum"] or 0
    net = row["net"] or 0
    hud["bb100"] = round(100.0 * net / bb, 2) if bb else 0
    hud["bb100_before"] = round(100.0 * (net + paid) / bb, 2) if bb else 0
    hud["first_hand"] = row["first_hand"]
    hud["last_hand"] = row["last_hand"]
    hud["won_hands"] = row["won_hands"] or 0
    hud["lost_hands"] = row["lost_hands"] or 0
    hud["game"] = args.get("game") or "all"
    return hud


def graph(conn: sqlite3.Connection, args: dict) -> dict:
    where, params = filters_sql(args)
    rows = conn.execute(
        f"""
        SELECT ts, played_at, hero_net, hero_collected, bb, pot,
               rake, jackpot, bingo, fortune, tax
        FROM hands
        WHERE {where}
        ORDER BY ts, id
        """,
        params,
    ).fetchall()
    points = []
    cum = 0
    gross = 0
    bb_cum = 0.0
    rake_paid = 0
    n = len(rows)
    step = max(1, n // 400) if n else 1
    for i, row in enumerate(rows, start=1):
        net = row["hero_net"] or 0
        share = hero_rake_paid_cents(row)
        rake_paid += share
        cum += net
        gross += net + share
        if row["bb"]:
            bb_cum += net / row["bb"]
        if i == 1 or i == n or i % step == 0:
            points.append(
                {
                    "i": i,
                    "t": row["played_at"],
                    "net": dollars(cum),
                    "gross": dollars(gross),
                    "bb": round(bb_cum, 2),
                }
            )
    if rows and (not points or points[-1]["i"] != n):
        points.append(
            {
                "i": n,
                "t": rows[-1]["played_at"],
                "net": dollars(cum),
                "gross": dollars(gross),
                "bb": round(bb_cum, 2),
            }
        )
    return {
        "points": points,
        "hands": n,
        "net": dollars(cum),
        "gross": dollars(gross),
        "rake_paid": dollars(rake_paid),
        "bb": round(bb_cum, 2),
    }


def sessions(conn: sqlite3.Connection, args: dict) -> list[dict]:
    where, params = filters_sql(args)
    rows = conn.execute(
        f"""
        SELECT s.id, s.started_at, s.ended_at, s.duration_sec,
               COUNT(h.id) AS hands, SUM(h.hero_net) AS net, SUM(h.bb) AS bb_sum,
               SUM(h.vpip) AS vpip, SUM(h.pfr) AS pfr, SUM(h.rake) AS rake
        FROM sessions s
        JOIN hands h ON h.session_id = s.id
        WHERE {where}
        GROUP BY s.id
        ORDER BY s.start_ts DESC
        """,
        params,
    ).fetchall()
    out = []
    for row in rows:
        hours = (row["duration_sec"] or 0) / 3600.0
        net = row["net"] or 0
        hud = hud_from_row(row)
        out.append(
            {
                "id": row["id"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "duration_min": round((row["duration_sec"] or 0) / 60.0, 1),
                "hands": row["hands"],
                "net": dollars(net),
                "bb100": hud["bb100"],
                "vpip": hud["vpip"],
                "pfr": hud["pfr"],
                "hourly": round(dollars(net) / hours, 2) if hours >= 0.08 else None,
                "rake": dollars(row["rake"]),
            }
        )
    return out


def hands(conn: sqlite3.Connection, args: dict) -> dict:
    where, params = filters_sql(args)
    page = max(1, int(args.get("page") or 1))
    size = min(100, max(10, int(args.get("page_size") or 40)))
    sort = args.get("sort") or "-ts"
    mapping = {
        "ts": "ts ASC, id ASC",
        "-ts": "ts DESC, id DESC",
        "net": "hero_net ASC",
        "-net": "hero_net DESC",
        "pot": "pot ASC",
        "-pot": "pot DESC",
    }
    order = mapping.get(sort, "ts DESC, id DESC")
    total = conn.execute(f"SELECT COUNT(*) AS n FROM hands WHERE {where}", params).fetchone()["n"]
    rows = conn.execute(
        f"""
        SELECT id, played_at, game_type, hero_pos, hero_cards, hand_key, board,
               players, pot, rake, hero_net, bb, vpip, pfr, threebet, saw_flop, wtsd,
               fold_street, session_id
        FROM hands
        WHERE {where}
        ORDER BY {order}
        LIMIT ? OFFSET ?
        """,
        [*params, size, (page - 1) * size],
    ).fetchall()
    return {
        "total": total,
        "page": page,
        "page_size": size,
        "rows": [
            {
                "id": r["id"],
                "played_at": r["played_at"],
                "game": r["game_type"],
                "pos": r["hero_pos"],
                "cards": r["hero_cards"],
                "hand": r["hand_key"],
                "board": r["board"],
                "players": r["players"],
                "pot": dollars(r["pot"]),
                "rake": dollars(r["rake"]),
                "net": dollars(r["hero_net"]),
                "bb": dollars(r["bb"]),
                "vpip": r["vpip"],
                "pfr": r["pfr"],
                "threebet": r["threebet"],
                "saw_flop": r["saw_flop"],
                "wtsd": r["wtsd"],
                "fold": r["fold_street"],
                "session": r["session_id"],
            }
            for r in rows
        ],
    }


def hand_detail(conn: sqlite3.Connection, hand_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM hands WHERE id = ?", (hand_id,)).fetchone()
    if not row:
        return None
    players = conn.execute(
        "SELECT * FROM player_hands WHERE hand_id = ? ORDER BY seat", (hand_id,)
    ).fetchall()
    from .parser import parse_hand

    parsed = parse_hand(row["raw"], row["source_file"] or "")
    replay = parsed.to_replay() if parsed else None
    return {
        "id": row["id"],
        "played_at": row["played_at"],
        "game": row["game"],
        "game_type": row["game_type"],
        "sb": dollars(row["sb"]),
        "bb": dollars(row["bb"]),
        "table": row["table_name"],
        "pos": row["hero_pos"],
        "cards": row["hero_cards"],
        "board": row["board"],
        "pot": dollars(row["pot"]),
        "rake": dollars(row["rake"]),
        "net": dollars(row["hero_net"]),
        "raw": row["raw"],
        "players": [
            {
                "name": p["name"],
                "hero": bool(p["is_hero"]),
                "seat": p["seat"],
                "position": p["position"],
                "stack": dollars(p["stack"]),
                "cards": p["cards"],
                "invested": dollars(p["invested"]),
                "collected": dollars(p["collected"]),
                "net": dollars(p["net"]),
            }
            for p in players
        ],
        "replay": replay,
    }


def positions(conn: sqlite3.Connection, args: dict) -> list[dict]:
    where, params = filters_sql(args)
    rows = conn.execute(
        f"""
        SELECT hero_pos AS pos,
               COUNT(*) AS hands,
               SUM(hero_net) AS net,
               SUM(bb) AS bb_sum,
               SUM(vpip) AS vpip, SUM(pfr) AS pfr,
               SUM(threebet) AS threebet, SUM(threebet_opp) AS threebet_opp,
               SUM(steal) AS steal, SUM(steal_opp) AS steal_opp,
               SUM(fold_to_steal) AS fold_to_steal, SUM(face_steal) AS face_steal,
               SUM(cbet_flop) AS cbet_flop, SUM(cbet_flop_opp) AS cbet_flop_opp,
               SUM(wtsd) AS wtsd, SUM(saw_flop) AS saw_flop, SUM(won_sd) AS won_sd,
               SUM(wwsf) AS wwsf, SUM(bets) AS bets, SUM(raises) AS raises, SUM(calls) AS calls,
               SUM(limp) AS limp, SUM(limp_opp) AS limp_opp
        FROM hands
        WHERE {where}
        GROUP BY hero_pos
        """,
        params,
    ).fetchall()
    by_pos = {r["pos"]: hud_from_row(r) | {"pos": r["pos"]} for r in rows}
    return [by_pos[p] for p in POS_ORDER if p in by_pos] + [
        by_pos[p] for p in by_pos if p not in POS_ORDER
    ]


def starting_hands(conn: sqlite3.Connection, args: dict) -> list[dict]:
    where, params = filters_sql(args)
    rows = conn.execute(
        f"""
        SELECT hand_key AS k, COUNT(*) AS hands, SUM(hero_net) AS net, SUM(bb) AS bb_sum,
               SUM(vpip) AS vpip, SUM(pfr) AS pfr, SUM(saw_flop) AS saw_flop, SUM(wtsd) AS wtsd
        FROM hands
        WHERE {where} AND hand_key != ''
        GROUP BY hand_key
        """,
        params,
    ).fetchall()
    return [
        {
            "hand": r["k"],
            "hands": r["hands"],
            "net": dollars(r["net"]),
            "bb100": hud_from_row(r)["bb100"],
            "vpip": _pct(r["vpip"], r["hands"]),
            "pfr": _pct(r["pfr"], r["hands"]),
        }
        for r in rows
    ]


def time_of_day(conn: sqlite3.Connection, args: dict) -> list[dict]:
    where, params = filters_sql(args)
    rows = conn.execute(
        f"""
        SELECT CAST(substr(played_at, 12, 2) AS INTEGER) AS hour,
               COUNT(*) AS hands, SUM(hero_net) AS net, SUM(bb) AS bb_sum,
               SUM(vpip) AS vpip, SUM(pfr) AS pfr
        FROM hands
        WHERE {where}
        GROUP BY hour
        ORDER BY hour
        """,
        params,
    ).fetchall()
    return [
        {
            "hour": r["hour"],
            "hands": r["hands"],
            "net": dollars(r["net"]),
            "bb100": hud_from_row(r)["bb100"],
            "vpip": _pct(r["vpip"], r["hands"]),
            "pfr": _pct(r["pfr"], r["hands"]),
        }
        for r in rows
    ]


def daily(conn: sqlite3.Connection, args: dict) -> list[dict]:
    where, params = filters_sql(args)
    rows = conn.execute(
        f"""
        SELECT substr(played_at, 1, 10) AS day,
               COUNT(*) AS hands, SUM(hero_net) AS net, SUM(bb) AS bb_sum,
               SUM(vpip) AS vpip, SUM(pfr) AS pfr, SUM(rake) AS rake
        FROM hands
        WHERE {where}
        GROUP BY day
        ORDER BY day
        """,
        params,
    ).fetchall()
    return [
        {
            "day": r["day"],
            "hands": r["hands"],
            "net": dollars(r["net"]),
            "bb100": hud_from_row(r)["bb100"],
            "vpip": _pct(r["vpip"], r["hands"]),
            "pfr": _pct(r["pfr"], r["hands"]),
            "rake": dollars(r["rake"]),
        }
        for r in rows
    ]


def players(conn: sqlite3.Connection, args: dict) -> dict:
    min_hands = int(args.get("min_hands") or 20)
    q = args.get("q") or ""
    page = max(1, int(args.get("page") or 1))
    size = min(100, max(10, int(args.get("page_size") or 40)))
    where = "name != 'Hero'"
    params: list = []
    if q:
        where += " AND name LIKE ?"
        params.append(f"%{q}%")
    total_row = conn.execute(
        f"SELECT COUNT(*) AS n FROM (SELECT name FROM player_hands WHERE {where} GROUP BY name HAVING COUNT(*) >= ?)",
        [*params, min_hands],
    ).fetchone()
    rows = conn.execute(
        f"""
        SELECT name, COUNT(*) AS hands,
               SUM(net) AS net,
               SUM(vpip) AS vpip, SUM(pfr) AS pfr,
               SUM(threebet) AS threebet, SUM(threebet_opp) AS threebet_opp,
               SUM(fold_to_3bet) AS fold_to_3bet, SUM(fold_to_3bet_opp) AS fold_to_3bet_opp,
               SUM(steal) AS steal, SUM(steal_opp) AS steal_opp,
               SUM(cbet_flop) AS cbet_flop, SUM(cbet_flop_opp) AS cbet_flop_opp,
               SUM(fold_to_cbet) AS fold_to_cbet, SUM(face_cbet) AS face_cbet,
               SUM(wtsd) AS wtsd, SUM(saw_flop) AS saw_flop, SUM(won_sd) AS won_sd,
               SUM(bets) AS bets, SUM(raises) AS raises, SUM(calls) AS calls
        FROM player_hands
        WHERE {where}
        GROUP BY name
        HAVING COUNT(*) >= ?
        ORDER BY hands DESC, net ASC
        LIMIT ? OFFSET ?
        """,
        [*params, min_hands, size, (page - 1) * size],
    ).fetchall()
    return {
        "total": total_row["n"],
        "page": page,
        "rows": [
            {"name": r["name"], **hud_from_row(r)}
            for r in rows
        ],
    }


def leaks(conn: sqlite3.Connection, args: dict) -> list[dict]:
    hud = summary(conn, args)
    findings = []

    def add(key, value, unit="%"):
        if value is None:
            return
        spec = BENCHMARKS[key]
        low, high = spec["low"], spec["high"]
        status = "ok"
        if value < low:
            status = "low"
        elif value > high:
            status = "high"
        findings.append(
            {
                "key": key,
                "label": spec["label"],
                "value": value,
                "unit": spec["unit"],
                "low": low,
                "high": high,
                "status": status,
                "note": spec[f"{status}_note"],
            }
        )

    add("vpip", hud["vpip"])
    add("pfr", hud["pfr"])
    if hud["vpip"] is not None and hud["pfr"] is not None:
        add("gap", round(hud["vpip"] - hud["pfr"], 2), "pp")
    add("threebet", hud["threebet"])
    add("fold_to_3bet", hud["fold_to_3bet"])
    add("steal", hud["steal"])
    add("fold_to_steal", hud["fold_to_steal"])
    add("cbet_flop", hud["cbet_flop"])
    add("fold_to_cbet", hud["fold_to_cbet"])
    add("wtsd", hud["wtsd"])
    add("wsd", hud["wsd"])
    add("af", hud["af"], "x")
    findings.sort(key=lambda x: (0 if x["status"] != "ok" else 1, x["label"]))
    return findings


def extrema(conn: sqlite3.Connection, args: dict) -> dict:
    where, params = filters_sql(args)
    wins = conn.execute(
        f"""
        SELECT id, played_at, hero_pos, hero_cards, board, hero_net, pot
        FROM hands WHERE {where} ORDER BY hero_net DESC LIMIT 8
        """,
        params,
    ).fetchall()
    losses = conn.execute(
        f"""
        SELECT id, played_at, hero_pos, hero_cards, board, hero_net, pot
        FROM hands WHERE {where} ORDER BY hero_net ASC LIMIT 8
        """,
        params,
    ).fetchall()

    def pack(rows):
        return [
            {
                "id": r["id"],
                "played_at": r["played_at"],
                "pos": r["hero_pos"],
                "cards": r["hero_cards"],
                "board": r["board"],
                "net": dollars(r["hero_net"]),
                "pot": dollars(r["pot"]),
            }
            for r in rows
        ]

    return {"wins": pack(wins), "losses": pack(losses)}
