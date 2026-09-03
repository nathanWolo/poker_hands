"""Preflop leak scan vs published 6-max 100bb cash GTO charts."""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "poker.db"

RANKS = "AKQJT98765432"

# Approximate GTO Wizard-style 100bb 6-max cash RFI (raise if unopened).
# Mixed combos included if solvers typically raise them >25%.
GTO_RFI = {
    "UTG": (
        "22+,A2s+,ATo+,KTs+,KQo,QTs+,JTs,T9s,98s,87s,76s,65s"
    ),
    "HJ": (
        "22+,A2s+,ATo+,K9s+,KJo+,Q9s+,J9s+,T9s,98s,87s,76s,65s,54s,QJo"
    ),
    "CO": (
        "22+,A2s+,ATo+,K9s+,KTo+,Q9s+,J9s+,T8s+,97s+,86s+,76s,65s,54s,QJo,JTo"
    ),
    "BTN": (
        "22+,A2s+,A9o+,K5s+,KTo+,Q7s+,QTo+,J7s+,JTo,T7s+,T9o,97s+,87s,76s,65s,54s,K9o,Q9o"
    ),
    "SB": (
        "22+,A2s+,A9o+,K6s+,KTo+,Q8s+,QTo+,J8s+,JTo,T8s+,97s+,87s,76s,65s,54s,K9o"
    ),
}

# Hands that are clear folds from UTG in 100bb GTO (never or <<10% raise).
UTG_JUNK_EXAMPLES = {"KJo", "K9s", "QJo", "Q9s", "JTo", "T9o", "A9o", "A8o", "A5o", "KTo", "22", "33"}  # 22-33 mixed in some solves; keep 22+ in range

# BB defend vs BTN steal: very wide (~40%+). We'll flag calling the worst offsuit junk.


def expand(spec: str) -> set[str]:
    out: set[str] = set()
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if token.endswith("+") and len(token) == 3 and token[0] == token[1]:
            i = RANKS.index(token[0])
            for r in RANKS[: i + 1]:
                out.add(r + r)
        elif token.endswith("+") and len(token) >= 4 and token[2] in "so":
            high, low, sh = token[0], token[1], token[2]
            ih, il = RANKS.index(high), RANKS.index(low)
            for r in RANKS[ih + 1 : il + 1]:
                out.add(high + r + sh)
        elif len(token) in (2, 3):
            out.add(token)
        else:
            out.add(token.rstrip("+"))
    return out


GTO_SETS = {pos: expand(spec) for pos, spec in GTO_RFI.items()}


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def dollars(cents):
    return round((cents or 0) / 100.0, 2)


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    job_note = None
    try:
        # not in sqlite
        pass
    except Exception:
        pass

    hud = conn.execute(
        """
        SELECT COUNT(*) AS hands,
               SUM(hero_net) AS net, SUM(bb) AS bb_sum,
               SUM(vpip) AS vpip, SUM(pfr) AS pfr,
               SUM(threebet) AS threebet, SUM(threebet_opp) AS threebet_opp,
               SUM(fold_to_3bet) AS f3, SUM(fold_to_3bet_opp) AS f3o,
               SUM(call_3bet) AS c3,
               SUM(fourbet) AS fourbet, SUM(fourbet_opp) AS fourbet_opp,
               SUM(steal) AS steal, SUM(steal_opp) AS steal_opp,
               SUM(fold_to_steal) AS fsteal, SUM(face_steal) AS face_steal,
               SUM(limp) AS limp, SUM(limp_opp) AS limp_opp
        FROM hands WHERE game_type='NLHE'
        """
    ).fetchone()

    pos_rows = conn.execute(
        """
        SELECT hero_pos AS pos, COUNT(*) AS hands,
               SUM(hero_net) AS net, SUM(bb) AS bb_sum,
               SUM(vpip) AS vpip, SUM(pfr) AS pfr,
               SUM(threebet) AS threebet, SUM(threebet_opp) AS threebet_opp,
               SUM(fold_to_3bet) AS f3, SUM(fold_to_3bet_opp) AS f3o,
               SUM(call_3bet) AS c3,
               SUM(fourbet) AS fourbet, SUM(fourbet_opp) AS fourbet_opp,
               SUM(steal) AS steal, SUM(steal_opp) AS steal_opp,
               SUM(fold_to_steal) AS fsteal, SUM(face_steal) AS face_steal,
               SUM(limp) AS limp, SUM(limp_opp) AS limp_opp
        FROM hands WHERE game_type='NLHE'
        GROUP BY hero_pos
        """
    ).fetchall()

    rfi = conn.execute(
        """
        SELECT hero_pos AS pos, hand_key AS k,
               COUNT(*) AS n,
               SUM(CASE WHEN limp_opp=1 THEN 1 ELSE 0 END) AS opp,
               SUM(CASE WHEN limp_opp=1 AND pfr=1 AND threebet=0 AND fourbet=0 THEN 1 ELSE 0 END) AS opens,
               SUM(CASE WHEN limp_opp=1 AND vpip=0 THEN 1 ELSE 0 END) AS folds,
               SUM(CASE WHEN limp_opp=1 AND limp=1 THEN 1 ELSE 0 END) AS limps,
               SUM(hero_net) AS net
        FROM hands
        WHERE game_type='NLHE' AND hand_key != ''
        GROUP BY hero_pos, hand_key
        """
    ).fetchall()

    vs3 = conn.execute(
        """
        SELECT hero_pos AS pos, hand_key AS k,
               SUM(fold_to_3bet_opp) AS opp,
               SUM(fold_to_3bet) AS folds,
               SUM(call_3bet) AS calls,
               SUM(fourbet) AS fourbets,
               SUM(hero_net) AS net
        FROM hands
        WHERE game_type='NLHE' AND hand_key != ''
        GROUP BY hero_pos, hand_key
        """
    ).fetchall()

    steal_bb = conn.execute(
        """
        SELECT hand_key AS k,
               SUM(face_steal) AS faced,
               SUM(fold_to_steal) AS folds,
               SUM(CASE WHEN face_steal=1 AND threebet=1 THEN 1 ELSE 0 END) AS threebets,
               SUM(CASE WHEN face_steal=1 AND vpip=1 AND threebet=0 AND fold_to_steal=0 THEN 1 ELSE 0 END) AS calls,
               SUM(hero_net) AS net
        FROM hands
        WHERE game_type='NLHE' AND hero_pos='BB' AND hand_key != ''
        GROUP BY hand_key
        """
    ).fetchall()

    stack = conn.execute(
        """
        SELECT AVG(ph.stack * 1.0 / h.bb) AS avg_bb,
               MIN(h.bb) AS bb
        FROM player_hands ph JOIN hands h ON h.id = ph.hand_id
        WHERE ph.is_hero=1 AND h.game_type='NLHE' AND h.bb > 0
        """
    ).fetchone()

    reviews = conn.execute("SELECT COUNT(*) AS n, SUM(ev_lost_cents) AS ev FROM solver_reviews").fetchone()

    pos_order = ["UTG", "HJ", "CO", "BTN", "SB", "BB"]
    by_pos = []
    for p in pos_order:
        r = next((x for x in pos_rows if x["pos"] == p), None)
        if not r:
            continue
        by_pos.append(
            {
                "pos": p,
                "hands": r["hands"],
                "net": dollars(r["net"]),
                "vpip": pct(r["vpip"], r["hands"]),
                "pfr": pct(r["pfr"], r["hands"]),
                "rfi": pct(r["pfr"] - (r["threebet"] or 0) - (r["fourbet"] or 0), r["hands"])
                if r["hands"]
                else None,
                "threebet": pct(r["threebet"], r["threebet_opp"]),
                "fold_to_3bet": pct(r["f3"], r["f3o"]),
                "call_3bet": pct(r["c3"], r["threebet_opp"]),
                "steal": pct(r["steal"], r["steal_opp"]),
                "fold_vs_steal": pct(r["fsteal"], r["face_steal"]),
                "limp": pct(r["limp"], r["limp_opp"]),
                "bb100": round(100.0 * (r["net"] or 0) / r["bb_sum"], 1) if r["bb_sum"] else None,
            }
        )

    # Off-range opens and missed opens vs GTO RFI chart
    off = []
    missed = []
    by_pos_rfi = defaultdict(lambda: {"opp": 0, "opens": 0, "in_gto": 0, "off": 0})
    for row in rfi:
        pos, k = row["pos"], row["k"]
        if pos not in GTO_SETS or not row["opp"]:
            continue
        gto = GTO_SETS[pos]
        by_pos_rfi[pos]["opp"] += row["opp"]
        by_pos_rfi[pos]["opens"] += row["opens"]
        if row["opens"] and k not in gto:
            by_pos_rfi[pos]["off"] += row["opens"]
            off.append(
                {
                    "pos": pos,
                    "hand": k,
                    "opens": row["opens"],
                    "opp": row["opp"],
                    "freq": pct(row["opens"], row["opp"]),
                    "net": dollars(row["net"]),
                }
            )
        if k in gto:
            by_pos_rfi[pos]["in_gto"] += row["opens"]
            if row["folds"]:
                missed.append(
                    {
                        "pos": pos,
                        "hand": k,
                        "folds": row["folds"],
                        "opp": row["opp"],
                        "open_freq": pct(row["opens"], row["opp"]),
                        "net": dollars(row["net"]),
                    }
                )

    off.sort(key=lambda x: (-x["opens"], x["net"]))
    missed.sort(key=lambda x: (-x["folds"], x["net"]))

    rfi_summary = []
    gto_rfi_freq = {"UTG": 16, "HJ": 20, "CO": 27, "BTN": 44, "SB": 42}
    for p in pos_order:
        s = by_pos_rfi[p]
        if not s["opp"]:
            continue
        rfi_summary.append(
            {
                "pos": p,
                "hero": pct(s["opens"], s["opp"]),
                "gto": gto_rfi_freq.get(p),
                "off_chart": pct(s["off"], s["opens"]) if s["opens"] else 0,
                "n": s["opp"],
            }
        )

    # vs 3bet: hands you call that are typically folds
    call3 = []
    for row in vs3:
        if not row["opp"]:
            continue
        if row["calls"]:
            call3.append(
                {
                    "pos": row["pos"],
                    "hand": row["k"],
                    "opp": row["opp"],
                    "calls": row["calls"],
                    "folds": row["folds"],
                    "fourbets": row["fourbets"],
                    "net": dollars(row["net"]),
                    "call_pct": pct(row["calls"], row["opp"]),
                }
            )
    call3.sort(key=lambda x: (x["net"], -x["calls"]))

    # BB vs steal worst calls
    bb_calls = []
    bb_tot = {"faced": 0, "folds": 0, "calls": 0, "threebets": 0, "net": 0}
    for row in steal_bb:
        bb_tot["faced"] += row["faced"] or 0
        bb_tot["folds"] += row["folds"] or 0
        bb_tot["calls"] += row["calls"] or 0
        bb_tot["threebets"] += row["threebets"] or 0
        bb_tot["net"] += row["net"] or 0
        if row["calls"]:
            bb_calls.append(
                {
                    "hand": row["k"],
                    "faced": row["faced"],
                    "calls": row["calls"],
                    "folds": row["folds"],
                    "threebets": row["threebets"],
                    "net": dollars(row["net"]),
                }
            )
    bb_calls.sort(key=lambda x: x["net"])

    worst_vpip = conn.execute(
        """
        SELECT hand_key AS k, hero_pos AS pos, COUNT(*) AS n, SUM(hero_net) AS net,
               SUM(vpip) AS vpip, SUM(pfr) AS pfr
        FROM hands
        WHERE game_type='NLHE' AND vpip=1 AND hand_key != ''
        GROUP BY hand_key, hero_pos
        HAVING n >= 8
        ORDER BY net ASC
        LIMIT 20
        """
    ).fetchall()

    out = {
        "hands": hud["hands"],
        "net": dollars(hud["net"]),
        "avg_stack_bb": round(stack["avg_bb"] or 0, 1),
        "reviews": reviews["n"],
        "review_ev": dollars(reviews["ev"]),
        "overall": {
            "vpip": pct(hud["vpip"], hud["hands"]),
            "pfr": pct(hud["pfr"], hud["hands"]),
            "gap": round(pct(hud["vpip"], hud["hands"]) - pct(hud["pfr"], hud["hands"]), 1),
            "threebet": pct(hud["threebet"], hud["threebet_opp"]),
            "fold_to_3bet": pct(hud["f3"], hud["f3o"]),
            "call_3bet": pct(hud["c3"], hud["threebet_opp"]),
            "fourbet": pct(hud["fourbet"], hud["fourbet_opp"]),
            "steal": pct(hud["steal"], hud["steal_opp"]),
            "fold_vs_steal": pct(hud["fsteal"], hud["face_steal"]),
            "limp": pct(hud["limp"], hud["limp_opp"]),
        },
        "by_pos": by_pos,
        "rfi": rfi_summary,
        "off_range_opens": off[:25],
        "missed_opens": missed[:20],
        "call_3bet_leaks": [x for x in call3 if x["calls"] >= 3][:15],
        "bb_vs_steal": {
            "faced": bb_tot["faced"],
            "fold": pct(bb_tot["folds"], bb_tot["faced"]),
            "call": pct(bb_tot["calls"], bb_tot["faced"]),
            "threebet": pct(bb_tot["threebets"], bb_tot["faced"]),
            "net": dollars(bb_tot["net"]),
        },
        "bb_worst_calls": bb_calls[:15],
        "worst_played": [
            {
                "hand": r["k"],
                "pos": r["pos"],
                "n": r["n"],
                "net": dollars(r["net"]),
                "vpip": pct(r["vpip"], r["n"]),
                "pfr": pct(r["pfr"], r["n"]),
            }
            for r in worst_vpip
        ],
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
