from engine import db
from engine.importer import import_path
from tests.hh import fold_preflop, hero_steal


def _write(path, *texts: str) -> None:
    path.write_text("\n".join(texts), encoding="utf-8")


def test_reimport_same_file_skips_duplicates(conn, tmp_path):
    src = tmp_path / "a.txt"
    _write(src, fold_preflop("RC1", "2026/08/01 12:00:00"), hero_steal("RC2", "2026/08/01 12:05:00"))

    first = import_path(conn, src)
    assert first["parsed"] == 2
    assert first["inserted"] == 2
    assert first["skipped"] == 0
    assert first["total"] == 2
    assert first["sessions"] >= 1

    second = import_path(conn, src)
    assert second["parsed"] == 2
    assert second["inserted"] == 0
    assert second["skipped"] == 2
    assert second["total"] == 2
    assert db.hand_count(conn) == 2


def test_overlapping_files_in_one_folder(conn, tmp_path):
    folder = tmp_path / "dump"
    folder.mkdir()
    _write(
        folder / "old.txt",
        fold_preflop("RC1", "2026/08/01 12:00:00"),
        hero_steal("RC2", "2026/08/01 12:05:00"),
    )
    _write(
        folder / "overlap.txt",
        hero_steal("RC2", "2026/08/01 12:05:00"),
        fold_preflop("RC3", "2026/08/02 12:00:00"),
    )

    result = import_path(conn, folder)
    assert result["parsed"] == 4
    assert result["inserted"] == 3
    assert result["skipped"] == 1
    assert result["total"] == 3
    ids = [r["id"] for r in conn.execute("SELECT id FROM hands ORDER BY id")]
    assert ids == ["RC1", "RC2", "RC3"]


def test_duplicate_hand_twice_in_same_txt(conn, tmp_path):
    src = tmp_path / "dup.txt"
    hand = fold_preflop("RC9", "2026/08/01 12:00:00")
    _write(src, hand, hand)
    result = import_path(conn, src)
    assert result["parsed"] == 2
    assert result["inserted"] == 1
    assert result["skipped"] == 1
    assert db.hand_count(conn) == 1
