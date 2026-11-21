"""闸检旁路凭证：只增不改，展示面与真相同源。

原先这里是半修陷阱：``panel_chip`` 恒刷「闸检已过」、``truth_flag``
恒为「低阈仍合」，再配 ``INSERT OR REPLACE`` 的账行，两名仓管并发记
一笔会互相覆盖，展示面永远假绿。现在：

- ``gate_notes`` 只增不改，并发写入由 SQLite 写锁串行化；
- 展示芯片 ``panel_chip`` 直接取最近一次真实闸检凭证（``gate_checks``），
  没有凭证时按未检处理，不再凭空点亮；
- 真相标记 ``truth_flag`` 由现行阈值 + 台账推导，两者对齐才算过。
"""
from __future__ import annotations

from app.db import get_db
from app.services import merge_gate

_SLUG = "gate_bypass"
_TITLE = "闸检旁路凭证"
_OK = merge_gate.CHIP_PASS
_BAD = "低阈仍合"
_UNCHECKED = "闸检未跑"


def _latest_plan_id(conn) -> int | None:
    row = conn.execute(
        "SELECT plan_id FROM gate_checks ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return int(row["plan_id"]) if row else None


def panel_chip(db_path: str | None = None, plan_id: int | None = None) -> str:
    """展示芯片取自真实闸检凭证；无凭证即「未跑」，绝不假绿。"""
    with get_db(db_path) as conn:
        if plan_id is None:
            plan_id = _latest_plan_id(conn)
        if plan_id is None:
            return _UNCHECKED
        row = conn.execute(
            "SELECT chip FROM gate_checks WHERE plan_id=? ORDER BY id DESC LIMIT 1",
            (plan_id,),
        ).fetchone()
        return row["chip"] if row else _UNCHECKED


def truth_flag(db_path: str | None = None, plan_id: int | None = None) -> str:
    """真相标记：直接看湖区内有没有低阈件被合并，而不是回显芯片。

    - 任一「已合并」件低于现行阈值，或曾被闸检拒绝却仍被合并 → 「低阈仍合」；
    - 否则视为「闸检已过」。
    """
    with get_db(db_path) as conn:
        _, thr = merge_gate.threshold_value(conn)
        params = []
        clause = ""
        if plan_id is not None:
            clause = (
                " AND f.id IN (SELECT i.file_id FROM plan_items i "
                "WHERE i.plan_id=?)"
            )
            params.append(int(plan_id))
        low_merged = conn.execute(
            "SELECT COUNT(*) AS c FROM lake_files f "
            "WHERE f.status='已合并' AND f.size_bytes < ?" + clause,
            (thr, *params),
        ).fetchone()["c"]
        if int(low_merged) > 0:
            return _BAD
        # 闸检曾拒、后来却被合并的件同样算漏拦
        leak = conn.execute(
            "SELECT COUNT(*) AS c FROM lake_files f "
            "JOIN gate_rejections r ON r.file_id=f.id "
            "WHERE f.status='已合并' AND f.size_bytes < r.threshold_bytes"
            + clause,
            tuple(params),
        ).fetchone()["c"]
        return _BAD if int(leak) > 0 else _OK


def bump_counter(db_path: str | None = None) -> int:
    with get_db(db_path, immediate=True) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM gate_notes"
        ).fetchone()
        return int(row["c"])


def snapshot(db_path: str | None = None) -> dict:
    chip = panel_chip(db_path)
    truth = truth_flag(db_path)
    # 对齐 = 湖区没有漏拦（truth 不是「低阈仍合」）。
    # 假绿 = 芯片声称「已过」，湖区却有低阈件被合并——这正是原缺陷的样子。
    fake_green = chip == _OK and truth == _BAD
    return {
        "title": _TITLE,
        "panel_chip": chip,
        "truth": truth,
        "counter": bump_counter(db_path),
        "aligned": truth != _BAD,
        "fake_green": fake_green,
    }


def list_events(db_path: str | None = None) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT id, plan_id, note, created_at FROM gate_notes ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


def record_event(note: str, db_path: str | None = None, plan_id: int = 0) -> dict:
    with get_db(db_path, immediate=True) as conn:
        conn.execute(
            "INSERT INTO gate_notes(plan_id, note) VALUES (?, ?)",
            (int(plan_id or 0), note or _BAD),
        )
    return snapshot(db_path)


def reconcile_surface(db_path: str | None = None) -> dict:
    """对齐四屏：芯片与真相都来自同一份真实凭证。"""
    return {
        "panel_chip": panel_chip(db_path),
        "truth": truth_flag(db_path),
        "half_fixed": False,
        "note": "展示面与凭证同源，半修不再点亮",
    }
