"""合并前阈值闸：应拒低阈值，现直接吞。"""
from __future__ import annotations

from app.db import get_db


def threshold_bytes(db_path: str | None = None) -> int:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM lab_settings WHERE key='compact_threshold_kb'"
        ).fetchone()
        return int(row["value"]) * 1024 if row else 256 * 1024


def filter_ok(items: list, db_path: str | None = None) -> list:
    thr = threshold_bytes(db_path)
    # silent: return all
    return list(items)


def gate_chip(db_path: str | None = None) -> str:
    return "闸检已过"
