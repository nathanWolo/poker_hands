"""Find heads-up postflop lines that disagree most with TexasSolver GTO.

TexasSolver dumps action frequencies, not chip EVs. Estimated EV lost is
(GTO frequency of the best action − frequency of the action you took) × pot.
Taking the solver's top action scores 0; a 0% GTO line ranks as a leak.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
import threading

from . import db
from .db import filters_sql
from .parser import parse_hand
from . import solver

VOL = {"fold", "check", "call", "bet", "raise"}
REPLAY_TYPES = ("sb", "bb", "post", "fold", "check", "call", "bet", "raise", "uncalled", "collect", "show")
_CACHE_MAX_CHARS = 1_500_000
_SIZE_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)")

_job_lock = threading.Lock()
_job = {
    "state": "idle",
    "done": 0,
    "total": 0,
    "solved": 0,
    "failed": 0,
    "message": "",
    "preset": "audit",
    "all": False,
}


def job_status() -> dict:
    with _job_lock:
        return dict(_job)


def reset_job() -> None:
    _set_job(state="idle", done=0, total=0, solved=0, failed=0, message="", preset="audit", all=False)


def _set_job(**kwargs) -> None:
    with _job_lock:
        _job.update(kwargs)


def action_chips(label: str) -> float | None:
    if not label:
        return None
    m = _SIZE_RE.search(label)
    if m:
        return float(m.group(1))
    return None


def classify_gto_label(label: str) -> str:
    up = (label or "").upper()
    if up.startswith("CHECK"):
        return "check"
    if up.startswith("FOLD"):
        return "fold"
    if up.startswith("CALL"):
        return "call"
    if "ALLIN" in up or "ALL-IN" in up or up.startswith("BET") or up.startswith("RAISE"):
        return "bet"
    return "other"


def match_gto_action(hero_act, gto_actions: list[str]) -> str | None:
    if not hero_act or not gto_actions:
        return None
    t = hero_act.type
    if t == "check":
        return next((a for a in gto_actions if a.upper().startswith("CHECK")), None)
    if t == "fold":
        return next((a for a in gto_actions if a.upper().startswith("FOLD")), None)
    if t == "call":
        return next((a for a in gto_actions if a.upper().startswith("CALL")), None)
    if t not in ("bet", "raise"):
        return None
    sized = []
    allin = None
    for label in gto_actions:
        if classify_gto_label(label) != "bet":
            continue
        up = label.upper()
        chips = action_chips(label)
        if chips is None or "ALLIN" in up or "ALL-IN" in up:
            allin = label
        else:
            sized.append((abs(chips - (hero_act.amount or 0)), chips, label))
    if hero_act.allin and allin:
        return allin
    if sized:
        sized.sort()
        return sized[0][2]
    return allin


def match_child_key(villain_act, keys: list[str]) -> str | None:
    if not villain_act:
        return None
    fake = type(
        "A",
        (),
        {"type": villain_act.type, "amount": villain_act.amount, "allin": getattr(villain_act, "allin", False)},
    )
    return match_gto_action(fake, keys)


def _usable_node(node) -> bool:
    if not isinstance(node, dict):
        return False
    if node.get("node_type") == "action_node":
        return True
    return bool(node.get("strategy") or node.get("actions"))


def select_strategy_node(tree: dict, hero_role: str, villain_act) -> dict | None:
    if not tree:
        return None
    if hero_role == "oop" or villain_act is None:
        return tree if _usable_node(tree) or tree.get("actions") is not None else tree
    kids = tree.get("childrens") or {}
    key = match_child_key(villain_act, list(kids.keys()))
    node = kids.get(key) if key else None
    return node if _usable_node(node) else None


def score_combo(node: dict, hero_cards: str, hero_act) -> dict:
    actions = list(node.get("actions") or (node.get("strategy") or {}).get("actions") or [])
    table = (node.get("strategy") or {}).get("strategy") or {}
    combo, freqs = solver.lookup_combo(table, hero_cards)
    in_range = combo is not None
    if not freqs:
        freqs = [0.0] * len(actions)
    matched = match_gto_action(hero_act, actions)
    freq_map = dict(zip(actions, freqs))
    gto_freq = float(freq_map.get(matched, 0.0)) if matched else 0.0
    best_label, best_freq = None, -1.0
    for lab, fr in freq_map.items():
        if fr > best_freq:
            best_label, best_freq = lab, float(fr)
    return {
        "combo": combo,
        "in_range": in_range,
        "gto_match": matched,
        "gto_freq": round(gto_freq, 4),
        "gto_best": best_label,
        "gto_best_freq": round(best_freq, 4) if best_freq >= 0 else 0.0,
        "actions": actions,
        "freqs": [round(float(x), 4) for x in freqs],
    }


def street_vol_actions(hand, street: str):
    return [a for a in hand.actions if a.street == street and a.type in VOL]


def hero_line(hand, street: str, role: str, oop_name: str, hero_name: str):
    acts = street_vol_actions(hand, street)
    if role == "oop":
        for a in acts:
            if a.player == hero_name:
                return a, None
        return None, None
    vill = None
    for a in acts:
        if vill is None and a.player == oop_name:
            vill = a
            continue
        if vill is not None and a.player == hero_name:
            return a, vill
    return None, None


def item_from_hand_row(row) -> dict | None:
    hand = parse_hand(row["raw"] or "", "")
    if not hand:
        return None
    spot = solver.spot_from_hand(hand)
    if not spot.get("ok") or not spot.get("hero_role"):
        return None
    if int(spot.get("pot") or 0) <= 0:
        return None
    hero = hand.hero_seat()
    if not hero:
        return None
    hero_act, vill_act = hero_line(
        hand, spot["street"], spot["hero_role"], spot["oop"]["name"], hero.name
    )
    if not hero_act:
        return None
    return {
        "hand_id": row["id"],
        "net": row["hero_net"] or 0,
        "hero_pos": row["hero_pos"] or "",
        "bb": row["bb"] or 0,
        "hero_act": hero_act,
        "vill_act": vill_act,
        "spot": spot,
        "hand": hand,
        "hero_name": hero.name,
    }


def decision_replay_index(hand, street: str, hero_name: str) -> int | None:
    acts = [a for a in hand.actions if a.type in REPLAY_TYPES]
    for i, a in enumerate(acts):
        if a.street == street and a.player == hero_name and a.type in VOL:
            return i
    return None


def collect_hu_spots(conn: sqlite3.Connection, args: dict | None = None) -> list[dict]:
    where, params = filters_sql(args or {})
    rows = conn.execute(
        f"""
        SELECT id, raw, hero_net, hero_pos, hero_cards, bb
        FROM hands
        WHERE ({where}) AND game_type = 'NLHE' AND saw_flop = 1
        """,
        params,
    ).fetchall()
    out = []
    for row in rows:
        item = item_from_hand_row(row)
        if item:
            out.append(item)
    return out


def _review_count(conn: sqlite3.Connection, args: dict | None = None) -> int:
    where, params = filters_sql(args or {})
    try:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS n FROM solver_reviews
            WHERE hand_id IN (SELECT id FROM hands WHERE {where})
            """,
            params,
        ).fetchone()
        return int(row["n"] if row else 0)
    except sqlite3.OperationalError:
        return 0


def catalog(conn: sqlite3.Connection, args: dict | None = None) -> dict:
    spots = collect_hu_spots(conn, args)
    by_street = defaultdict(int)
    by_role = defaultdict(int)
    for s in spots:
        by_street[s["spot"]["street"]] += 1
        by_role[s["spot"]["hero_role"]] += 1
    worst = sorted(spots, key=lambda s: s["net"])[:8]
    return {
        "eligible": len(spots),
        "by_street": dict(by_street),
        "by_role": dict(by_role),
        "note": (
            "TexasSolver is HU postflop only. Estimated EV is "
            "(GTO freq of its best action − freq of your action) × pot — not true chip EV. "
            "Analysis solves a sample of your worst realized pots, not every hand."
        ),
        "sample_losses": [
            {
                "id": s["hand_id"],
                "net": round((s["net"] or 0) / 100.0, 2),
                "street": s["spot"]["street"],
                "role": s["spot"]["hero_role"],
                "pos": s["hero_pos"],
                "pot": round(s["spot"]["pot"] / 100.0, 2),
                "action": s["hero_act"].type,
            }
            for s in worst
        ],
        "job": job_status(),
        "reviews": _review_count(conn, args),
        "installed": bool(solver.console_exe()),
    }


def _cache_key(spot: dict, preset: str) -> str:
    raw = "|".join(
        [
            solver.format_board(spot["board"]),
            str(int(spot["pot"])),
            str(int(spot["effective_stack"])),
            preset,
        ]
    )
    return hashlib.sha1(raw.encode()).hexdigest()


def _cached_tree(conn: sqlite3.Connection, key: str) -> dict | None:
    row = conn.execute("SELECT result_json FROM solver_cache WHERE cache_key = ?", (key,)).fetchone()
    if not row:
        return None
    return json.loads(row["result_json"])


def _store_tree(conn: sqlite3.Connection, key: str, tree: dict) -> None:
    payload = json.dumps(tree)
    if len(payload) > _CACHE_MAX_CHARS:
        return
    conn.execute(
        "INSERT OR REPLACE INTO solver_cache (cache_key, result_json, created_at) VALUES (?, ?, ?)",
        (key, payload, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def _save_review(conn: sqlite3.Connection, rec: dict) -> None:
    mix = rec.get("mix") or {}
    conn.execute(
        """
        INSERT OR REPLACE INTO solver_reviews (
            hand_id, street, hero_role, hero_pos, hero_cards, hero_action, hero_action_type,
            gto_match, gto_freq, gto_best, gto_best_freq, ev_lost_cents, pot, board,
            in_range, note, net, updated_at, gto_mix
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rec["hand_id"], rec["street"], rec["hero_role"], rec["hero_pos"], rec["hero_cards"],
            rec["hero_action"], rec["hero_action_type"], rec["gto_match"], rec["gto_freq"],
            rec["gto_best"], rec["gto_best_freq"], rec["ev_lost_cents"], rec["pot"], rec["board"],
            rec["in_range"], rec["note"], rec["net"], rec["updated_at"],
            json.dumps(mix),
        ),
    )
    conn.commit()


def pick_spots(spots: list[dict], limit: int, by: str = "loss") -> list[dict]:
    if by == "pot":
        ordered = sorted(spots, key=lambda s: -s["spot"]["pot"])
    else:
        ordered = sorted(spots, key=lambda s: (s["net"], -s["spot"]["pot"]))
    if int(limit) <= 0:
        return ordered
    limit = max(1, min(int(limit), 40))
    if by == "loss":
        lost = [s for s in ordered if (s["net"] or 0) < 0]
        ordered = lost or ordered
    return ordered[:limit]


def review_spot(conn: sqlite3.Connection, item: dict, preset: str) -> dict:
    spot = item["spot"]
    key = _cache_key(spot, preset)
    tree = _cached_tree(conn, key)
    if tree is None:
        solved = solver.run_solve(spot, preset=preset, include_tree=True)
        if not solved.get("ok"):
            return {"ok": False, "error": solved.get("error") or "solve failed", "hand_id": item["hand_id"]}
        tree = solved["tree"]
        _store_tree(conn, key, tree)
    node = select_strategy_node(tree, spot["hero_role"], item["vill_act"])
    if not node:
        return {
            "ok": False,
            "error": "Villain line is not in the dumped tree (try a higher dump / quality preset).",
            "hand_id": item["hand_id"],
        }
    scored = score_combo(node, spot["hero_cards"], item["hero_act"])
    pot = int(spot["pot"])
    note = ""
    if not scored["in_range"]:
        note = "Hero combo is not in the default GTO range."
        ev_lost = 0
    elif scored["gto_match"] is None:
        note = "Your sizing is off the solver tree."
        ev_lost = round(max(0.0, scored["gto_best_freq"]) * pot)
    else:
        ev_lost = round(max(0.0, scored["gto_best_freq"] - scored["gto_freq"]) * pot)
        if scored["gto_freq"] < 0.05:
            note = "GTO almost never takes this line with your hand."
    rec = {
        "ok": True,
        "hand_id": item["hand_id"],
        "street": spot["street"],
        "hero_role": spot["hero_role"],
        "hero_pos": item["hero_pos"],
        "hero_cards": spot["hero_cards"],
        "hero_action": f"{item['hero_act'].type}" + (f" {item['hero_act'].amount}" if item["hero_act"].amount else ""),
        "hero_action_type": item["hero_act"].type,
        "gto_match": scored["gto_match"] or "",
        "gto_freq": scored["gto_freq"],
        "gto_best": scored["gto_best"] or "",
        "gto_best_freq": scored["gto_best_freq"],
        "ev_lost_cents": ev_lost,
        "pot": pot,
        "board": spot["board_text"],
        "in_range": 1 if scored["in_range"] else 0,
        "note": note,
        "net": item["net"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "mix": {"actions": scored["actions"], "freqs": scored["freqs"]},
    }
    _save_review(conn, rec)
    return rec


def start_analyze(args: dict | None = None, limit: int = 12, preset: str = "audit", by: str = "loss") -> dict:
    with _job_lock:
        if _job["state"] == "running":
            return {"ok": False, "error": "An analysis is already running.", **dict(_job)}
        _job.update(
            state="running",
            done=0,
            total=0,
            solved=0,
            failed=0,
            message="Scanning hands…",
            preset=preset,
            all=int(limit) <= 0,
        )
    thread = threading.Thread(
        target=_analyze_worker,
        args=(dict(args or {}), int(limit), preset, by),
        daemon=True,
    )
    thread.start()
    return {"ok": True, **job_status()}


def _reviewed_with_mix(conn: sqlite3.Connection) -> set[str]:
    try:
        rows = conn.execute(
            "SELECT hand_id FROM solver_reviews WHERE gto_mix IS NOT NULL AND length(gto_mix) > 2"
        ).fetchall()
    except sqlite3.OperationalError:
        return set()
    return {r["hand_id"] for r in rows}


def _analyze_worker(args: dict, limit: int, preset: str, by: str) -> None:
    conn = db.connect()
    try:
        db.init(conn)
        spots = collect_hu_spots(conn, args)
        all_mode = int(limit) <= 0
        chosen = pick_spots(spots, limit, by=by) if spots else []
        if all_mode and chosen:
            already = _reviewed_with_mix(conn)
            skipped = sum(1 for s in chosen if s["hand_id"] in already)
            chosen = [s for s in chosen if s["hand_id"] not in already]
            if skipped:
                _set_job(message=f"Resuming — {skipped} already scored, {len(chosen)} remaining…")
        if not chosen:
            _set_job(state="done", total=0, done=0, message="No HU postflop spots left to solve in this filter.")
            return
        if not solver.console_exe():
            _set_job(state="error", total=len(chosen), message="TexasSolver is not installed.")
            return
        if not all_mode:
            where, params = filters_sql(args)
            conn.execute(
                f"DELETE FROM solver_reviews WHERE hand_id IN (SELECT id FROM hands WHERE {where})",
                params,
            )
            conn.commit()
        _set_job(total=len(chosen), message=f"Solving {len(chosen)} spots with {preset} preset…")
        solved = failed = 0
        for i, item in enumerate(chosen, start=1):
            _set_job(done=i - 1, message=f"Solving {item['hand_id']} ({i}/{len(chosen)})")
            rec = review_spot(conn, item, preset)
            if rec.get("ok"):
                solved += 1
            else:
                failed += 1
            _set_job(done=i, solved=solved, failed=failed)
        _set_job(state="done", message=f"Reviewed {solved} spots, {failed} failed.")
    except Exception as exc:
        _set_job(state="error", message=str(exc))
    finally:
        conn.close()


def _row_to_review(row) -> dict:
    mix = {}
    raw_mix = None
    try:
        raw_mix = row["gto_mix"]
    except (KeyError, IndexError):
        raw_mix = None
    if raw_mix:
        try:
            mix = json.loads(raw_mix)
        except json.JSONDecodeError:
            mix = {}
    return {
        "ok": True,
        "hand_id": row["hand_id"],
        "street": row["street"],
        "hero_role": row["hero_role"],
        "hero_pos": row["hero_pos"],
        "hero_cards": row["hero_cards"],
        "hero_action": row["hero_action"],
        "hero_action_type": row["hero_action_type"],
        "gto_match": row["gto_match"] or "",
        "gto_freq": row["gto_freq"],
        "gto_best": row["gto_best"] or "",
        "gto_best_freq": row["gto_best_freq"],
        "ev_lost": round((row["ev_lost_cents"] or 0) / 100.0, 2),
        "pot": round((row["pot"] or 0) / 100.0, 2),
        "board": row["board"] or "",
        "in_range": bool(row["in_range"]),
        "note": row["note"] or "",
        "net": round((row["net"] or 0) / 100.0, 2),
        "mix": mix if isinstance(mix, dict) else {},
    }


def get_review(conn: sqlite3.Connection, hand_id: str) -> dict | None:
    try:
        row = conn.execute("SELECT * FROM solver_reviews WHERE hand_id = ?", (hand_id,)).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    rec = _row_to_review(row)
    hand_row = conn.execute("SELECT id, raw, hero_net, hero_pos, hero_cards, bb FROM hands WHERE id = ?", (hand_id,)).fetchone()
    if not hand_row:
        return rec
    item = item_from_hand_row(hand_row)
    if not item:
        return rec
    rec["decision_index"] = decision_replay_index(item["hand"], rec["street"] or item["spot"]["street"], item["hero_name"])
    rec["hero_name"] = item["hero_name"]
    mix = rec.get("mix") or {}
    if not mix.get("actions"):
        for preset in ("quick", "audit", "fast", "normal", "quality"):
            if _cached_tree(conn, _cache_key(item["spot"], preset)):
                filled = review_spot(conn, item, preset)
                if filled.get("ok"):
                    rec = _row_to_review(
                        conn.execute("SELECT * FROM solver_reviews WHERE hand_id = ?", (hand_id,)).fetchone()
                    )
                    rec["decision_index"] = decision_replay_index(
                        item["hand"], rec["street"] or item["spot"]["street"], item["hero_name"]
                    )
                    rec["hero_name"] = item["hero_name"]
                break
    return rec


def leak_report(conn: sqlite3.Connection, args: dict | None = None) -> dict:
    where, params = filters_sql(args or {})
    try:
        rows = conn.execute(
            f"""
            SELECT r.* FROM solver_reviews r
            WHERE r.hand_id IN (SELECT id FROM hands WHERE {where})
            ORDER BY r.ev_lost_cents DESC, r.net ASC
            """,
            params,
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    packed = []
    street = defaultdict(lambda: {"n": 0, "ev": 0})
    role = defaultdict(lambda: {"n": 0, "ev": 0})
    action = defaultdict(lambda: {"n": 0, "ev": 0})
    pos = defaultdict(lambda: {"n": 0, "ev": 0})
    total = 0
    for r in rows:
        ev = r["ev_lost_cents"] or 0
        total += ev
        rec = {
            "id": r["hand_id"],
            "street": r["street"],
            "role": r["hero_role"],
            "pos": r["hero_pos"],
            "cards": r["hero_cards"],
            "board": r["board"],
            "action": r["hero_action"],
            "gto_match": r["gto_match"],
            "gto_freq": r["gto_freq"],
            "gto_best": r["gto_best"],
            "gto_best_freq": r["gto_best_freq"],
            "ev_lost": round(ev / 100.0, 2),
            "pot": round((r["pot"] or 0) / 100.0, 2),
            "net": round((r["net"] or 0) / 100.0, 2),
            "in_range": bool(r["in_range"]),
            "note": r["note"] or "",
        }
        packed.append(rec)
        street[r["street"] or "?"]["n"] += 1
        street[r["street"] or "?"]["ev"] += ev
        role[r["hero_role"] or "?"]["n"] += 1
        role[r["hero_role"] or "?"]["ev"] += ev
        action[r["hero_action_type"] or "?"]["n"] += 1
        action[r["hero_action_type"] or "?"]["ev"] += ev
        pos[r["hero_pos"] or "?"]["n"] += 1
        pos[r["hero_pos"] or "?"]["ev"] += ev

    def pack(d):
        items = [
            {"key": k, "n": v["n"], "ev_lost": round(v["ev"] / 100.0, 2)}
            for k, v in d.items()
        ]
        items.sort(key=lambda x: -x["ev_lost"])
        return items

    return {
        "spots": len(packed),
        "ev_lost": round(total / 100.0, 2),
        "by_street": pack(street),
        "by_role": pack(role),
        "by_action": pack(action),
        "by_pos": pack(pos),
        "worst": packed[:25],
        "job": job_status(),
        "note": (
            "Estimate = (GTO frequency of its best action − frequency of your action) × pot. "
            "Villain is given a default 6-max cash range, so treat this as a ranking of mismatches, not exact chip EV."
        ),
    }
