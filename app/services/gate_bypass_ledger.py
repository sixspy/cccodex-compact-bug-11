"""闸检旁路凭证账：只增不改，写入即回正主路径。

``append_ledger`` 原先用 ``INSERT OR REPLACE`` 写 ``meta`` 的固定键，
两名仓管并发记一笔会互相覆盖，页面上只看到最后一条。现在改落到
``gate_notes`` 只增表，并返回与之同源的展示芯片/真相，避免「账记了
但芯片仍假绿」的两张皮。
"""
from __future__ import annotations

from app.db import get_db
from app.services import merge_gate
from app.services.gate_bypass_surface import (
    panel_chip,
    record_event,
    snapshot,
    truth_flag,
)

_TITLE = "闸检旁路凭证"
_OK = merge_gate.CHIP_PASS


def append_ledger(plan_id: int, note: str, db_path: str | None = None) -> dict:
    with get_db(db_path, immediate=True) as conn:
        conn.execute(
            "INSERT INTO gate_notes(plan_id, note) VALUES (?, ?)",
            (int(plan_id or 0), note or _TITLE),
        )
    record_event(f"plan={plan_id} {note}", db_path, plan_id=plan_id)
    summary = merge_gate.summarize(plan_id, db_path) if plan_id else None
    return {
        "plan_id": plan_id,
        "note": note,
        "panel": panel_chip(db_path, plan_id=plan_id or None),
        "truth": truth_flag(db_path, plan_id=plan_id or None),
        "gate": summary,
    }


def ledger_rows(db_path: str | None = None, plan_id: int | None = None) -> list[dict]:
    with get_db(db_path) as conn:
        if plan_id is None:
            rows = conn.execute(
                "SELECT id, plan_id, note, created_at FROM gate_notes ORDER BY id"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, plan_id, note, created_at FROM gate_notes "
                "WHERE plan_id=? ORDER BY id",
                (plan_id,),
            ).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "plan_id": r["plan_id"],
                    "value": r["note"],
                    "created_at": r["created_at"],
                    "chip": panel_chip(db_path, plan_id=r["plan_id"] or None),
                }
            )
        return out


def dashboard(db_path: str | None = None, plan_id: int | None = None) -> dict:
    snap = snapshot(db_path)
    with get_db(db_path) as conn:
        gate_rows = conn.execute(
            "SELECT id, plan_id, threshold_kb, accepted_files, rejected_files, "
            "result, chip, message, created_at FROM gate_checks "
            "ORDER BY id DESC LIMIT 20"
        ).fetchall()
        rejection_rows = conn.execute(
            "SELECT r.id, r.plan_id, r.file_id, f.path, r.size_bytes, "
            "r.threshold_bytes, r.reason, r.created_at "
            "FROM gate_rejections r LEFT JOIN lake_files f ON f.id=r.file_id "
            "ORDER BY r.id DESC LIMIT 50"
        ).fetchall()
    return {
        "title": _TITLE,
        "chip": snap["panel_chip"],
        "truth": snap["truth"],
        "aligned": snap["aligned"],
        "rows": ledger_rows(db_path, plan_id=plan_id),
        "checks": [dict(r) for r in gate_rows],
        "rejections": [dict(r) for r in rejection_rows],
        "ok_chip": _OK,
        "bad_chip": "低阈仍合",
        "fake_green": snap["fake_green"],
    }
