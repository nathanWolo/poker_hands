"""TexasSolver (https://github.com/bupticybee/TexasSolver) console wrapper.

Heads-up postflop only. Invokes the official Windows binary — we do not
vendor TexasSolver source (AGPL). Pot and stack are chip units (we use cents).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time

from .parser import ParsedHand, Seat, starting_hand_key

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "tools" / "texassolver" / "bin"
WORKDIR = ROOT / "data" / "solver"
ZIP_URL = "https://github.com/bupticybee/TexasSolver/releases/download/v0.2.0/TexasSolver-v0.2.0-Windows.zip"
ZIP_NAME = "TexasSolver-v0.2.0-Windows.zip"

RANGE_IP = (
    "AA,KK,QQ,JJ,TT,99:0.75,88:0.75,77:0.5,66:0.25,55:0.25,AK,AQs,AQo:0.75,"
    "AJs,AJo:0.5,ATs:0.75,A6s:0.25,A5s:0.75,A4s:0.75,A3s:0.5,A2s:0.5,KQs,"
    "KQo:0.5,KJs,KTs:0.75,K5s:0.25,K4s:0.25,QJs:0.75,QTs:0.75,Q9s:0.5,JTs:"
    "0.75,J9s:0.75,J8s:0.75,T9s:0.75,T8s:0.75,T7s:0.75,98s:0.75,97s:0.75,"
    "96s:0.5,87s:0.75,86s:0.5,85s:0.5,76s:0.75,75s:0.5,65s:0.75,64s:0.5,"
    "54s:0.75,53s:0.5,43s:0.5"
)
RANGE_OOP = (
    "QQ:0.5,JJ:0.75,TT,99,88,77,66,55,44,33,22,AKo:0.25,AQs,AQo:0.75,AJs,"
    "AJo:0.75,ATs,ATo:0.75,A9s,A8s,A7s,A6s,A5s,A4s,A3s,A2s,KQ,KJ,KTs,KTo:0.5,"
    "K9s,K8s,K7s,K6s,K5s,K4s:0.5,K3s:0.5,K2s:0.5,QJ,QTs,Q9s,Q8s,Q7s,JTs,"
    "JTo:0.5,J9s,J8s,T9s,T8s,T7s,98s,97s,96s,87s,86s,76s,75s,65s,64s,54s,"
    "53s,43s"
)

PRESETS = {
    "quick": {"accuracy": 8.0, "max_iteration": 8, "dump_rounds": 1, "timeout": 30},
    "audit": {"accuracy": 5.0, "max_iteration": 12, "dump_rounds": 1, "timeout": 60},
    "fast": {"accuracy": 2.0, "max_iteration": 40, "dump_rounds": 1, "timeout": 90},
    "normal": {"accuracy": 1.0, "max_iteration": 100, "dump_rounds": 1, "timeout": 180},
    "quality": {"accuracy": 0.5, "max_iteration": 200, "dump_rounds": 2, "timeout": 300},
}

DEFAULT_BET_LINES = [
    "set_bet_sizes oop,flop,bet,50",
    "set_bet_sizes oop,flop,raise,60",
    "set_bet_sizes oop,flop,allin",
    "set_bet_sizes ip,flop,bet,50",
    "set_bet_sizes ip,flop,raise,60",
    "set_bet_sizes ip,flop,allin",
    "set_bet_sizes oop,turn,bet,50",
    "set_bet_sizes oop,turn,raise,60",
    "set_bet_sizes oop,turn,allin",
    "set_bet_sizes ip,turn,bet,50",
    "set_bet_sizes ip,turn,raise,60",
    "set_bet_sizes ip,turn,allin",
    "set_bet_sizes oop,river,bet,50",
    "set_bet_sizes oop,river,donk,50",
    "set_bet_sizes oop,river,raise,60,100",
    "set_bet_sizes oop,river,allin",
    "set_bet_sizes ip,river,bet,50",
    "set_bet_sizes ip,river,raise,60,100",
    "set_bet_sizes ip,river,allin",
]


def console_exe() -> Path | None:
    exe = BIN / "console_solver.exe"
    return exe if exe.is_file() else None


def gui_exe() -> Path | None:
    exe = BIN / "TexasSolverGui.exe"
    return exe if exe.is_file() else None


def status() -> dict:
    exe = console_exe()
    gui = gui_exe()
    return {
        "installed": bool(exe),
        "console": str(exe) if exe else None,
        "gui": str(gui) if gui else None,
        "resources": str(BIN / "resources") if (BIN / "resources").is_dir() else None,
        "presets": list(PRESETS),
        "license": "TexasSolver is AGPL-3.0; this tracker calls the official binary.",
    }


def load_bundled_ranges() -> tuple[str, str]:
    path = BIN / "parameters" / "sample_parameters" / "default_parameters.txt"
    ip, oop = RANGE_IP, RANGE_OOP
    if not path.is_file():
        return ip, oop
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("set_range_ip "):
            ip = line.split(" ", 1)[1].strip()
        elif line.startswith("set_range_oop "):
            oop = line.split(" ", 1)[1].strip()
    return ip, oop


def format_board(cards: list[str] | str) -> str:
    if isinstance(cards, str):
        parts = [c for c in cards.replace(",", " ").split() if c]
    else:
        parts = [c for c in cards if c]
    return ",".join(parts)


def combo_keys(cards: list[str] | str) -> list[str]:
    if isinstance(cards, str):
        parts = [c for c in cards.replace(",", " ").split() if c]
    else:
        parts = list(cards)
    if len(parts) < 2:
        return []
    a, b = parts[0], parts[1]
    return [a + b, b + a]


def lookup_combo(table: dict, cards: list[str] | str) -> tuple[str | None, list[float] | None]:
    for key in combo_keys(cards):
        if key in table:
            return key, [float(x) for x in table[key]]
    return None, None


def actor_label(player: int | None) -> str:
    # TexasSolver dumps OOP (first to act) as player 1.
    if player == 1:
        return "oop"
    if player == 0:
        return "ip"
    return "unknown"


def summarize_node(node: dict, hero_cards: str | list[str] | None = None, limit: int = 80) -> dict:
    actions = list(node.get("actions") or node.get("strategy", {}).get("actions") or [])
    table = (node.get("strategy") or {}).get("strategy") or {}
    mixes = []
    totals = [0.0] * len(actions)
    n = 0
    for combo, freqs in table.items():
        row = [float(x) for x in freqs]
        if len(row) != len(actions):
            continue
        mixes.append(
            {
                "combo": combo,
                "hand": starting_hand_key([combo[:2], combo[2:4]]) if len(combo) >= 4 else combo,
                "freqs": [round(x, 4) for x in row],
            }
        )
        for i, x in enumerate(row):
            totals[i] += x
        n += 1
    avg = [round(t / n, 4) for t in totals] if n else []
    hero_key, hero_freq = lookup_combo(table, hero_cards) if hero_cards else (None, None)
    mixes.sort(key=lambda r: r["hand"])
    return {
        "player": node.get("player"),
        "actor": actor_label(node.get("player")),
        "actions": actions,
        "average": dict(zip(actions, avg)) if actions and avg else {},
        "hero": {"combo": hero_key, "freqs": [round(x, 4) for x in hero_freq]} if hero_freq else None,
        "combos": mixes[:limit],
        "combo_count": n,
    }


def summarize_result(tree: dict, hero_cards: str | list[str] | None = None) -> dict:
    root = summarize_node(tree, hero_cards)
    after_check = None
    kids = tree.get("childrens") or {}
    check = kids.get("CHECK") or kids.get("check")
    if isinstance(check, dict) and check.get("node_type") == "action_node":
        after_check = summarize_node(check, hero_cards)
    return {"root": root, "after_check": after_check}


def build_commands(spot: dict, result_path: Path, preset: str = "fast") -> str:
    cfg = PRESETS.get(preset) or PRESETS["fast"]
    board = format_board(spot["board"])
    pot = int(spot["pot"])
    stack = int(spot["effective_stack"])
    ip = (spot.get("range_ip") or RANGE_IP).replace(" ", "")
    oop = (spot.get("range_oop") or RANGE_OOP).replace(" ", "")
    threads = int(spot.get("threads") or min(8, os.cpu_count() or 4))
    accuracy = float(spot.get("accuracy") or cfg["accuracy"])
    iters = int(spot.get("max_iteration") or cfg["max_iteration"])
    dump_rounds = int(spot.get("dump_rounds") or cfg["dump_rounds"])
    out = result_path.as_posix()
    lines = [
        f"set_pot {pot}",
        f"set_effective_stack {stack}",
        f"set_board {board}",
        f"set_range_ip {ip}",
        f"set_range_oop {oop}",
        *DEFAULT_BET_LINES,
        "set_allin_threshold 0.67",
        "build_tree",
        f"set_thread_num {threads}",
        f"set_accuracy {accuracy}",
        f"set_max_iteration {iters}",
        "set_print_interval 20",
        "set_use_isomorphism 1",
        "start_solve",
        f"set_dump_rounds {dump_rounds}",
        f"dump_result {out}",
    ]
    return "\n".join(lines) + "\n"


def remaining_at(hand: ParsedHand, street: str) -> list[Seat]:
    folded: set[str] = set()
    for act in hand.actions:
        if act.street == street:
            break
        if act.type == "fold":
            folded.add(act.player)
    return [s for s in hand.seats if s.name not in folded]


def invested_before(hand: ParsedHand, street: str) -> dict[str, int]:
    inv = {s.name: 0 for s in hand.seats}
    for act in hand.actions:
        if act.street == street:
            break
        if act.type in ("sb", "bb", "post", "call", "bet", "raise"):
            inv[act.player] = inv.get(act.player, 0) + (act.amount or 0)
        elif act.type == "uncalled":
            inv[act.player] = max(0, inv.get(act.player, 0) - (act.amount or 0))
    return inv


def first_to_act(players: list[Seat], button: int) -> Seat:
    ordered = sorted(players, key=lambda s: s.seat)
    after = [s for s in ordered if s.seat > button]
    return (after + ordered)[0]


def spot_from_hand(hand: ParsedHand) -> dict:
    if hand.game_type != "NLHE":
        return {"ok": False, "error": "TexasSolver is Hold'em only (this hand is PLO)."}
    ip_range, oop_range = load_bundled_ranges()
    needed = {"flop": 3, "turn": 4, "river": 5}
    for street, n in needed.items():
        if len(hand.board) < n:
            continue
        left = remaining_at(hand, street)
        if len(left) != 2:
            continue
        inv = invested_before(hand, street)
        pot = sum(inv.values())
        stacks = []
        for seat in left:
            stacks.append(max(0, seat.stack - inv.get(seat.name, 0)))
        oop = first_to_act(left, hand.button)
        ip = next(s for s in left if s.name != oop.name)
        hero = hand.hero_seat()
        hero_role = None
        if hero:
            if hero.name == oop.name:
                hero_role = "oop"
            elif hero.name == ip.name:
                hero_role = "ip"
        return {
            "ok": True,
            "street": street,
            "board": hand.board[:n],
            "board_text": format_board(hand.board[:n]),
            "pot": pot,
            "effective_stack": min(stacks) if stacks else 0,
            "oop": {"name": oop.name, "position": oop.position, "hero": bool(oop.is_hero)},
            "ip": {"name": ip.name, "position": ip.position, "hero": bool(ip.is_hero)},
            "hero_cards": " ".join(hero.cards) if hero else "",
            "hero_role": hero_role,
            "range_ip": ip_range,
            "range_oop": oop_range,
            "note": "Villain range is a default 6-max cash guess — edit it before solving.",
        }
    return {
        "ok": False,
        "error": "Need a heads-up flop, turn, or river. TexasSolver does not solve 3-way or preflop trees.",
    }


def run_solve(spot: dict, preset: str = "fast", *, include_tree: bool = False) -> dict:
    exe = console_exe()
    if not exe:
        return {"ok": False, "error": "TexasSolver is not installed. Expected tools/texassolver/bin/console_solver.exe"}
    board = format_board(spot.get("board") or "")
    if board.count(",") not in (2, 3, 4):
        return {"ok": False, "error": "Board must be 3, 4, or 5 cards (flop/turn/river)."}
    if int(spot.get("pot") or 0) <= 0 or int(spot.get("effective_stack") or 0) <= 0:
        return {"ok": False, "error": "Pot and effective stack must be positive (chip units / cents)."}

    cfg = PRESETS.get(preset) or PRESETS["fast"]
    WORKDIR.mkdir(parents=True, exist_ok=True)
    result_path = WORKDIR / "last_result.json"
    cmd_path = WORKDIR / "last_commands.txt"
    text = build_commands(spot, result_path, preset=preset)
    cmd_path.write_text(text, encoding="utf-8")
    if result_path.exists():
        result_path.unlink()

    started = time.time()
    try:
        proc = subprocess.run(
            [
                str(exe),
                "--input_file",
                str(cmd_path),
                "--resource_dir",
                str(BIN / "resources"),
                "--mode",
                "holdem",
            ],
            cwd=str(BIN),
            capture_output=True,
            text=True,
            timeout=int(spot.get("timeout") or cfg["timeout"]),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Solver timed out after {cfg['timeout']}s. Try the fast preset or a smaller tree."}
    if proc.returncode != 0:
        tail = (proc.stdout or "")[-1500:] + "\n" + (proc.stderr or "")[-800:]
        return {"ok": False, "error": f"Solver exited {proc.returncode}", "log": tail.strip()}
    if not result_path.is_file():
        return {"ok": False, "error": "Solver finished but wrote no result file.", "log": (proc.stdout or "")[-1500:]}
    tree = json.loads(result_path.read_text(encoding="utf-8"))
    summary = summarize_result(tree, spot.get("hero_cards"))
    out = {
        "ok": True,
        "preset": preset,
        "spot": {
            "board": board,
            "pot": int(spot["pot"]),
            "effective_stack": int(spot["effective_stack"]),
            "hero_cards": spot.get("hero_cards") or "",
            "hero_role": spot.get("hero_role"),
        },
        "strategy": summary,
        "seconds": round(time.time() - started, 2),
        "log": _solver_log_tail(proc.stdout or ""),
    }
    if include_tree:
        out["tree"] = tree
    return out


def _solver_log_tail(stdout: str) -> str:
    keep = []
    for line in stdout.splitlines():
        if "START SOLVING" in line or line.startswith("Iter:") or "exploitability" in line or "Using" in line:
            keep.append(line)
    return "\n".join(keep[-30:])


def launch_gui() -> dict:
    exe = gui_exe()
    if not exe:
        return {"ok": False, "error": "TexasSolverGui.exe not found."}
    subprocess.Popen([str(exe)], cwd=str(BIN))
    return {"ok": True}


def install_windows_release(timeout: int = 180) -> dict:
    """Download and extract the official Windows zip into tools/texassolver/bin."""
    import zipfile
    import urllib.request
    import shutil

    dest_parent = ROOT / "tools" / "texassolver"
    dest_parent.mkdir(parents=True, exist_ok=True)
    zip_path = dest_parent / ZIP_NAME
    urllib.request.urlretrieve(ZIP_URL, zip_path)
    if BIN.exists():
        shutil.rmtree(BIN)
    BIN.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(BIN)
    inner = BIN / "TexasSolver-v0.2.0-Windows"
    if inner.is_dir():
        for item in inner.iterdir():
            item.rename(BIN / item.name)
        inner.rmdir()
    st = status()
    st["ok"] = st["installed"]
    return st
