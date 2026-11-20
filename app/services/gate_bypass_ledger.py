"""闸检绕过旁路账：写入不回正主路径。"""
from __future__ import annotations

from app.db import get_db
from app.services.gate_bypass_surface import panel_chip, record_event, snapshot, truth_flag

_SLUG = "gate_bypass"
_TITLE = "闸检绕过"
_OK = "闸检已过"


def append_ledger(plan_id: int, note: str, db_path: str | None = None) -> dict:
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (f"{_SLUG}_ledger_{plan_id}", note or _TITLE),
        )
    record_event(f"plan={plan_id} {note}", db_path)
    return {
        "plan_id": plan_id,
        "note": note,
        "panel": panel_chip(db_path),
        "truth": truth_flag(db_path),
    }


def ledger_rows(db_path: str | None = None) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT key, value FROM meta WHERE key LIKE ? ORDER BY key",
            (f"{_SLUG}_ledger_%",),
        ).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "key": r["key"],
                    "value": r["value"],
                    "chip": panel_chip(db_path),
                }
            )
        return out


def dashboard(db_path: str | None = None) -> dict:
    snap = snapshot(db_path)
    return {
        "title": _TITLE,
        "chip": snap["panel_chip"],
        "truth": snap["truth"],
        "rows": ledger_rows(db_path),
        "ok_chip": _OK,
        "bad_chip": "低阈仍合",
        "fake_green": snap["panel_chip"] == _OK and snap["truth"] != _OK,
    }
