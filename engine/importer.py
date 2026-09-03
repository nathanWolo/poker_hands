"""Import GGPoker zip archives and text hand histories into SQLite."""

from __future__ import annotations

from pathlib import Path
import zipfile

from . import db
from .parser import parse_file

ROOT = Path(__file__).resolve().parent.parent
IMPORTS = ROOT / "data" / "imports"
RAW = ROOT / "data" / "raw"


def read_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "utf-16", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def iter_zip_texts(path: Path):
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".txt"):
                continue
            with zf.open(info) as fh:
                yield Path(info.filename).name, read_text(fh.read())


def iter_folder_texts(path: Path):
    for file in sorted(path.rglob("*.txt")):
        yield file.name, read_text(file.read_bytes())


def import_path(conn, path: Path) -> dict:
    path = Path(path)
    texts = []
    if path.is_file() and path.suffix.lower() == ".zip":
        texts = list(iter_zip_texts(path))
    elif path.is_file() and path.suffix.lower() == ".txt":
        texts = [(path.name, read_text(path.read_bytes()))]
    elif path.is_dir():
        zips = list(path.glob("*.zip"))
        if zips:
            for z in zips:
                texts.extend(iter_zip_texts(z))
        else:
            texts = list(iter_folder_texts(path))
    else:
        return {
            "files": 0,
            "parsed": 0,
            "inserted": 0,
            "skipped": 0,
            "errors": 0,
            "sessions": db.session_count(conn),
            "total": db.hand_count(conn),
        }

    inserted = skipped = errors = parsed = 0
    batch = []
    for name, text in texts:
        hands = parse_file(text, name)
        parsed += len(hands)
        batch.extend(hands)
        if len(batch) >= 200:
            part = db.insert_hands(conn, batch)
            inserted += part["inserted"]
            skipped += part["skipped"]
            errors += part["errors"]
            batch = []
    if batch:
        part = db.insert_hands(conn, batch)
        inserted += part["inserted"]
        skipped += part["skipped"]
        errors += part["errors"]
    sessions = db.rebuild_sessions(conn) if inserted else db.session_count(conn)
    return {
        "files": len(texts),
        "parsed": parsed,
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
        "sessions": sessions,
        "total": db.hand_count(conn),
    }


def import_default(conn) -> dict:
    if IMPORTS.exists() and any(IMPORTS.glob("*.zip")):
        return import_path(conn, IMPORTS)
    if RAW.exists():
        return import_path(conn, RAW)
    return {
        "files": 0,
        "parsed": 0,
        "inserted": 0,
        "skipped": 0,
        "errors": 0,
        "sessions": db.session_count(conn),
        "total": db.hand_count(conn),
    }
