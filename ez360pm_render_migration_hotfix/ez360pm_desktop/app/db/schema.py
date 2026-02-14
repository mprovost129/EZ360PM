from __future__ import annotations

from pathlib import Path

from app.db.connection import connect


def apply_schema(schema_sql: str, db_path: Path | None = None) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()
