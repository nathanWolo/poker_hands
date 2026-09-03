from pathlib import Path
import time

import pytest

from engine import db
from tests.conftest import seed_dated_folds
from tests.hh import fold_preflop


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    path = tmp_path / "app.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    conn = db.init(db.connect(path))
    seed_dated_folds(conn)
    conn.close()

    from app import app

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_api_summary_date_query_params(client):
    all_h = client.get("/api/summary?game=NLHE").get_json()
    ranged = client.get(
        "/api/summary?game=NLHE&from=2026-08-01&to=2026-08-15"
    ).get_json()
    until = client.get("/api/summary?game=NLHE&to=2026-08-15").get_json()

    assert all_h["hands"] == 3
    assert ranged["hands"] == 1
    assert ranged["first_hand"].startswith("2026/08/10")
    assert until["hands"] == 2
    assert until["hands"] < all_h["hands"]


def test_api_import_skips_duplicates(client, tmp_path):
    from io import BytesIO

    text = fold_preflop("RC-NEW", "2026/08/12 12:00:00").encode("utf-8")
    first = client.post(
        "/api/import",
        data={"files": (BytesIO(text), "new.txt")},
        content_type="multipart/form-data",
    ).get_json()
    second = client.post(
        "/api/import",
        data={"files": (BytesIO(text), "new.txt")},
        content_type="multipart/form-data",
    ).get_json()
    assert first["inserted"] == 1
    assert first["skipped"] == 0
    assert second["inserted"] == 0
    assert second["skipped"] == 1
    assert second["total"] == first["total"]
    assert client.get("/api/health").get_json()["hands"] == 4


def test_api_solver_status(client):
    data = client.get("/api/solver/status").get_json()
    assert "installed" in data
    assert "fast" in data["presets"]
    assert "audit" in data["presets"]
    assert "quick" in data["presets"]


def test_api_solver_review_missing(client):
    res = client.get("/api/solver/review/nope")
    assert res.status_code == 404


def test_api_solver_catalog_and_leaks(client):
    cat = client.get("/api/solver/catalog?game=NLHE").get_json()
    assert cat["eligible"] == 0
    leaks = client.get("/api/solver/leaks?game=NLHE").get_json()
    assert leaks["spots"] == 0
    assert leaks["worst"] == []
    job = client.get("/api/solver/job").get_json()
    assert job["state"] in ("idle", "done", "error", "running")


def test_api_solver_analyze_no_spots(client):
    from engine import evleak

    evleak.reset_job()
    data = client.post(
        "/api/solver/analyze?game=NLHE",
        json={"limit": 4, "preset": "audit", "by": "loss"},
    ).get_json()
    assert data["ok"] is True
    job = None
    for _ in range(80):
        job = client.get("/api/solver/job").get_json()
        if job["state"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert job["state"] == "done"
    assert job["total"] == 0
    evleak.reset_job()
