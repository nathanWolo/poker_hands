from pathlib import Path

import pytest

from engine import db
from tests.hh import fold_preflop, hero_bb_defend_win, hero_steal, parse


@pytest.fixture
def conn(tmp_path: Path):
    c = db.init(db.connect(tmp_path / "poker.db"))
    yield c
    c.close()


def insert_text(conn, text: str) -> None:
    hand = parse(text)
    n = db.insert_hands(conn, [hand])
    assert n["inserted"] == 1


def seed_dated_folds(conn) -> None:
    """Three NLHE folds on three calendar days."""
    insert_text(conn, fold_preflop("RC-JUL", "2026/07/24 12:00:00"))
    insert_text(conn, fold_preflop("RC-AUG10", "2026/08/10 18:30:00"))
    insert_text(conn, fold_preflop("RC-AUG26", "2026/08/26 09:15:00", hero_cards="As Ah"))


def seed_mixed(conn) -> None:
    seed_dated_folds(conn)
    insert_text(conn, hero_steal("RC-STEAL", "2026/08/10 19:00:00"))
    insert_text(conn, hero_bb_defend_win("RC-WIN", "2026/08/11 21:00:00"))
    insert_text(
        conn,
        fold_preflop("PL-1", "2026/08/12 10:00:00", game="Omaha Pot Limit"),
    )
