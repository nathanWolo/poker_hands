"""Local PokerTracker-style analyzer for GGPoker hand histories."""

from __future__ import annotations

from pathlib import Path
import tempfile
import webbrowser
from threading import Timer

from flask import Flask, g, jsonify, request, send_from_directory

from engine import db, evleak, importer, solver, stats

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024


def get_conn():
    conn = getattr(g, "db_conn", None)
    if conn is None:
        conn = db.connect()
        g.db_conn = conn
    return conn


@app.teardown_appcontext
def close_conn(_exc):
    conn = getattr(g, "db_conn", None)
    if conn is not None:
        conn.close()


def args_dict():
    return {k: v for k, v in request.args.items() if v not in (None, "")}


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/api/health")
def health():
    conn = get_conn()
    return jsonify({"ok": True, "hands": db.hand_count(conn)})


@app.get("/api/summary")
def api_summary():
    return jsonify(stats.summary(get_conn(), args_dict()))


@app.get("/api/graph")
def api_graph():
    return jsonify(stats.graph(get_conn(), args_dict()))


@app.get("/api/sessions")
def api_sessions():
    return jsonify(stats.sessions(get_conn(), args_dict()))


@app.get("/api/hands")
def api_hands():
    return jsonify(stats.hands(get_conn(), args_dict()))


@app.get("/api/hands/<hand_id>")
def api_hand(hand_id: str):
    detail = stats.hand_detail(get_conn(), hand_id)
    if not detail:
        return jsonify({"error": "not found"}), 404
    return jsonify(detail)


@app.get("/api/positions")
def api_positions():
    return jsonify(stats.positions(get_conn(), args_dict()))


@app.get("/api/starting-hands")
def api_starting():
    return jsonify(stats.starting_hands(get_conn(), args_dict()))


@app.get("/api/time")
def api_time():
    return jsonify({"hours": stats.time_of_day(get_conn(), args_dict()), "days": stats.daily(get_conn(), args_dict())})


@app.get("/api/players")
def api_players():
    return jsonify(stats.players(get_conn(), args_dict()))


@app.get("/api/leaks")
def api_leaks():
    return jsonify(stats.leaks(get_conn(), args_dict()))


@app.get("/api/extrema")
def api_extrema():
    return jsonify(stats.extrema(get_conn(), args_dict()))


@app.post("/api/import")
def api_import():
    conn = get_conn()
    files = request.files.getlist("files")
    if not files:
        result = importer.import_default(conn)
        return jsonify(result)
    imported = {
        "files": 0,
        "parsed": 0,
        "inserted": 0,
        "skipped": 0,
        "errors": 0,
        "sessions": 0,
        "total": 0,
    }
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        for fs in files:
            name = Path(fs.filename or "upload.bin").name
            path = dest / name
            fs.save(path)
            part = importer.import_path(conn, path)
            imported["files"] += part.get("files", 0)
            imported["parsed"] += part.get("parsed", 0)
            imported["inserted"] += part.get("inserted", 0)
            imported["skipped"] += part.get("skipped", 0)
            imported["errors"] += part.get("errors", 0)
            imported["sessions"] = part.get("sessions", 0)
            imported["total"] = part.get("total", 0)
    return jsonify(imported)


@app.post("/api/rebuild")
def api_rebuild():
    conn = get_conn()
    db.reset_db(conn)
    result = importer.import_default(conn)
    return jsonify(result)


@app.get("/api/solver/status")
def api_solver_status():
    return jsonify(solver.status())


@app.get("/api/solver/from-hand/<hand_id>")
def api_solver_from_hand(hand_id: str):
    detail = stats.hand_detail(get_conn(), hand_id)
    if not detail or not detail.get("raw"):
        return jsonify({"ok": False, "error": "hand not found"}), 404
    from engine.parser import parse_hand

    parsed = parse_hand(detail["raw"], "")
    if not parsed:
        return jsonify({"ok": False, "error": "could not parse hand"}), 400
    return jsonify(solver.spot_from_hand(parsed) | {"hand_id": hand_id})


@app.post("/api/solver/run")
def api_solver_run():
    body = request.get_json(silent=True) or {}
    preset = body.get("preset") or "fast"
    return jsonify(solver.run_solve(body, preset=preset))


@app.post("/api/solver/gui")
def api_solver_gui():
    return jsonify(solver.launch_gui())


@app.get("/api/solver/catalog")
def api_solver_catalog():
    return jsonify(evleak.catalog(get_conn(), args_dict()))


@app.get("/api/solver/leaks")
def api_solver_leaks():
    return jsonify(evleak.leak_report(get_conn(), args_dict()))


@app.get("/api/solver/job")
def api_solver_job():
    return jsonify(evleak.job_status())


@app.get("/api/solver/review/<hand_id>")
def api_solver_review(hand_id: str):
    rec = evleak.get_review(get_conn(), hand_id)
    if not rec:
        return jsonify({"ok": False, "error": "no review for this hand"}), 404
    return jsonify(rec)


@app.post("/api/solver/analyze")
def api_solver_analyze():
    body = request.get_json(silent=True) or {}
    raw_limit = body.get("limit", request.args.get("limit", 12))
    if str(raw_limit).lower() in ("all", "0", ""):
        limit = 0
    else:
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            limit = 12
    preset = body.get("preset") or ("quick" if limit == 0 else "audit")
    by = body.get("by") or "loss"
    result = evleak.start_analyze(args_dict(), limit=limit, preset=preset, by=by)
    status = 409 if not result.get("ok") and evleak.job_status().get("state") == "running" else 200
    if not result.get("ok") and result.get("error"):
        return jsonify(result), status
    return jsonify(result)


def boot():
    conn = db.init()
    if db.hand_count(conn) == 0:
        print("No database yet — importing GGPoker zips from data/imports ...")
        result = importer.import_default(conn)
        print(
            f"Imported {result.get('inserted', 0)} hands "
            f"from {result.get('files', 0)} files "
            f"({result.get('sessions', 0)} sessions)."
        )
    else:
        print(f"Loaded existing database with {db.hand_count(conn)} hands.")
    conn.close()


def main():
    boot()
    port = 5050
    url = f"http://127.0.0.1:{port}"
    print(f"Tracker running at {url}")
    Timer(0.8, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
