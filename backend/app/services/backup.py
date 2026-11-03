"""SQLite-safe backup, integrity verification and restore helpers."""

import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from ..config import DATABASE_URL, DATA_DIR


def sqlite_database_path(database_url: str = DATABASE_URL) -> Path:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise ValueError("Backup and restore commands require a file-backed SQLite DATABASE_URL")
    return Path(url.database).resolve()


def verify_sqlite(path: str | Path) -> dict:
    target = Path(path).resolve()
    if not target.is_file():
        raise FileNotFoundError(target)
    connection = sqlite3.connect(str(target))
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")
        page_count = connection.execute("PRAGMA page_count").fetchone()[0]
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
    finally:
        connection.close()
    return {"path": str(target), "integrity": integrity, "page_count": page_count, "user_version": user_version}


def _unique_backup_path(output_dir: Path, timestamp: str) -> Path:
    base = output_dir / f"fdr_nexus.db.backup-{timestamp}"
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = output_dir / f"fdr_nexus.db.backup-{timestamp}-{suffix}"
        suffix += 1
    return candidate


def backup_database(source_path: str | Path | None = None, output_dir: str | Path | None = None) -> dict:
    source = Path(source_path).resolve() if source_path else sqlite_database_path()
    if not source.is_file():
        raise FileNotFoundError(source)
    destination_dir = Path(output_dir).resolve() if output_dir else DATA_DIR / "backups"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = _unique_backup_path(destination_dir, datetime.now().strftime("%Y%m%d-%H%M%S"))
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        source_connection = sqlite3.connect(str(source))
        destination_connection = sqlite3.connect(str(temporary))
        try:
            source_connection.execute("PRAGMA query_only=ON")
            source_connection.backup(destination_connection)
            destination_connection.commit()
        finally:
            source_connection.close()
            destination_connection.close()
        result = verify_sqlite(temporary)
        temporary.replace(destination)
        result["path"] = str(destination)
        result["source"] = str(source)
        return result
    finally:
        if temporary.exists():
            temporary.unlink()


def restore_database(backup_path: str | Path, target_path: str | Path, overwrite: bool = False) -> dict:
    backup = Path(backup_path).resolve()
    target = Path(target_path).resolve()
    verify_sqlite(backup)
    if target.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing database: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".restore.tmp")
    try:
        source_connection = sqlite3.connect(str(backup))
        target_connection = sqlite3.connect(str(temporary))
        try:
            source_connection.backup(target_connection)
            target_connection.commit()
        finally:
            source_connection.close()
            target_connection.close()
        result = verify_sqlite(temporary)
        temporary.replace(target)
        result["path"] = str(target)
        result["source"] = str(backup)
        return result
    finally:
        if temporary.exists():
            temporary.unlink()
