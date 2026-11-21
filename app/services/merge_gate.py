"""合并前阈值闸：闸检凭证 + 被拒件，闸检与阈值同源。

原先的问题：``filter_ok`` 原样返回全部碎件、``gate_chip`` 恒返回
「闸检已过」，于是低于阈值的碎件照样被吞进波次，台参数闸形同虚设。

现在只有一条轨：
- 闸检在合并入口的写事务内执行，闸检凭证落 ``gate_checks``；
- 低于阈值（或体积非法）的碎件落 ``gate_rejections`` 并给出原因；
- 闸检芯片、被拒原因、件表、合并队列都读同一份阈值与同一份凭证，
  不再有「只改提示不拦件」的半修余地。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.db import get_db

DEFAULT_THRESHOLD_KB = 256

RESULT_PASS = "通过"
RESULT_BLOCK = "拦截"
RESULT_ALL_REJECTED = "全拒"
RESULT_STALE = "失准"

CHIP_PASS = "闸检已过"
CHIP_BLOCK = "闸检拦下低阈件"
CHIP_ALL_REJECTED = "闸检全拒"
CHIP_STALE = "闸检失准"
CHIP_EMPTY = "闸检空计划"
CHIP_UNCHECKED = "闸检未跑"


@dataclass
class GateResult:
    """一次闸检的完整凭证。"""

    plan_id: int
    threshold_kb: int
    threshold_bytes: int
    total_files: int
    accepted: list = field(default_factory=list)
    rejected: list = field(default_factory=list)
    result: str = RESULT_PASS
    chip: str = CHIP_PASS
    message: str = ""
    note: str = ""
    gate_id: int | None = None

    @property
    def accepted_ids(self) -> list[int]:
        return [int(x["id"]) for x in self.accepted]

    @property
    def rejected_ids(self) -> list[int]:
        return [int(x["id"]) for x in self.rejected]

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)

    @property
    def accepted_count(self) -> int:
        return len(self.accepted)

    def accepted_bytes(self) -> int:
        return sum(int(x["size_bytes"]) for x in self.accepted)

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "gate_id": self.gate_id,
            "threshold_kb": self.threshold_kb,
            "threshold_bytes": self.threshold_bytes,
            "total_files": self.total_files,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "accepted_bytes": self.accepted_bytes(),
            "accepted_ids": self.accepted_ids,
            "rejected_ids": self.rejected_ids,
            "result": self.result,
            "chip": self.chip,
            "message": self.message,
            "note": self.note,
            "rejections": [dict(x) for x in self.rejected],
        }


def threshold_value(conn) -> tuple[int, int]:
    row = conn.execute(
        "SELECT value FROM lab_settings WHERE key='compact_threshold_kb'"
    ).fetchone()
    try:
        kb = int(str(row["value"]).strip()) if row else DEFAULT_THRESHOLD_KB
    except (TypeError, ValueError):
        kb = DEFAULT_THRESHOLD_KB
    if kb <= 0:
        kb = DEFAULT_THRESHOLD_KB
    return kb, kb * 1024


def threshold_bytes(db_path: str | None = None) -> int:
    with get_db(db_path) as conn:
        return threshold_value(conn)[1]


def threshold_kb(db_path: str | None = None) -> int:
    with get_db(db_path) as conn:
        return threshold_value(conn)[0]


def _rejection_reason(row, thr: int) -> str | None:
    """体积不合格的原因；合格返回 None。"""
    size = int(row["size_bytes"])
    if size <= 0:
        return f"体积非法：{size} 字节"
    if size < thr:
        return f"低于阈值：{size} 字节 < {thr} 字节"
    return None


def inspect(plan_id: int, conn, items: list, note: str = "") -> GateResult:
    """在给定连接（应为写事务）内跑闸检，不落库。

    ``items`` 为计划下待合并的碎件行；返回值同时给出合格件、被拒件与芯片。
    """
    kb, thr = threshold_value(conn)
    accepted: list = []
    rejected: list = []
    for row in items:
        reason = _rejection_reason(row, thr)
        if reason is None:
            accepted.append(row)
        else:
            rejected.append(
                {
                    "id": int(row["id"]),
                    "file_id": int(row["id"]),
                    "path": row["path"],
                    "table_name": row["table_name"],
                    "size_bytes": int(row["size_bytes"]),
                    "threshold_bytes": thr,
                    "reason": reason,
                }
            )

    res = GateResult(
        plan_id=plan_id,
        threshold_kb=kb,
        threshold_bytes=thr,
        total_files=len(items),
        accepted=accepted,
        rejected=rejected,
        note=note or "",
    )

    if not items:
        res.result = RESULT_ALL_REJECTED
        res.chip = CHIP_EMPTY
        res.message = "计划下无可合并碎文件"
    elif not accepted:
        res.result = RESULT_ALL_REJECTED
        res.chip = CHIP_ALL_REJECTED
        res.message = (
            f"闸检全拒：{len(rejected)} 个碎件均低于阈值 {kb} KB，未启动合并"
        )
    elif rejected:
        res.result = RESULT_BLOCK
        res.chip = CHIP_BLOCK
        res.message = (
            f"闸检拦下 {len(rejected)} 个低阈碎件（阈值 {kb} KB），"
            f"只合并 {len(accepted)} 个合格件"
        )
    else:
        res.result = RESULT_PASS
        res.chip = CHIP_PASS
        res.message = f"闸检已过：{len(accepted)} 个碎件均达阈值 {kb} KB"
    return res


def evaluate(plan_id: int, items: list, db_path: str | None = None, note: str = "") -> GateResult:
    """只读闸检：不落凭证，用于四屏展示同一套判定。"""
    with get_db(db_path) as conn:
        return inspect(plan_id, conn, items, note=note)


def write_credentials(conn, gate: GateResult) -> GateResult:
    """把闸检结果写成只增不改的凭证行与被拒件行。"""
    cur = conn.execute(
        "INSERT INTO gate_checks("
        "plan_id, threshold_kb, threshold_bytes, total_files, accepted_files, "
        "rejected_files, result, chip, message, accepted_ids, rejected_ids, note"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            gate.plan_id,
            gate.threshold_kb,
            gate.threshold_bytes,
            gate.total_files,
            gate.accepted_count,
            gate.rejected_count,
            gate.result,
            gate.chip,
            gate.message,
            json.dumps(gate.accepted_ids),
            json.dumps(gate.rejected_ids),
            gate.note,
        ),
    )
    gate.gate_id = int(cur.lastrowid)
    for row in gate.rejected:
        conn.execute(
            "INSERT INTO gate_rejections("
            "gate_id, plan_id, file_id, size_bytes, threshold_bytes, reason"
            ") VALUES (?,?,?,?,?,?)",
            (
                gate.gate_id,
                gate.plan_id,
                row["file_id"],
                row["size_bytes"],
                row["threshold_bytes"],
                row["reason"],
            ),
        )
    return gate


def latest_check(plan_id: int, db_path: str | None = None) -> dict | None:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM gate_checks WHERE plan_id=? ORDER BY id DESC LIMIT 1",
            (plan_id,),
        ).fetchone()
        return dict(row) if row else None


def list_rejections(plan_id: int, db_path: str | None = None) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT r.*, f.path, f.table_name FROM gate_rejections r "
            "LEFT JOIN lake_files f ON f.id=r.file_id "
            "WHERE r.gate_id=(SELECT MAX(g.id) FROM gate_checks g "
            " WHERE g.plan_id=?) ORDER BY r.id DESC",
            (plan_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def gate_chip(db_path: str | None = None, plan_id: int | None = None) -> str:
    """芯片取自最近一次真实闸检凭证；没跑过闸检就不点亮。"""
    if plan_id is None:
        return CHIP_UNCHECKED
    row = latest_check(plan_id, db_path)
    return row["chip"] if row else CHIP_UNCHECKED


def summarize(plan_id: int, db_path: str | None = None) -> dict:
    """四屏共用的计划闸检摘要：芯片、阈值、被拒件、最近凭证。

    被拒件只取最近一次闸检凭证下的行——阈值调整后重跑若已放行，
    旧拒绝不会继续挂在计划上造成芯片与拒件两张皮。
    """
    with get_db(db_path) as conn:
        kb, thr = threshold_value(conn)
        check = conn.execute(
            "SELECT chip, result, message, id FROM gate_checks "
            "WHERE plan_id=? ORDER BY id DESC LIMIT 1",
            (plan_id,),
        ).fetchone()
        rejections = []
        if check is not None:
            rejections = conn.execute(
                "SELECT r.file_id, r.size_bytes, r.threshold_bytes, r.reason, "
                "f.path, f.table_name FROM gate_rejections r "
                "LEFT JOIN lake_files f ON f.id=r.file_id "
                "WHERE r.gate_id=? ORDER BY r.id DESC",
                (check["id"],),
            ).fetchall()
    rejected = [dict(r) for r in rejections]
    return {
        "plan_id": plan_id,
        "threshold_kb": kb,
        "threshold_bytes": thr,
        "chip": check["chip"] if check else CHIP_UNCHECKED,
        "result": check["result"] if check else None,
        "message": check["message"] if check else "",
        "gate_id": check["id"] if check else None,
        "checked": check is not None,
        "rejected_count": len(rejected),
        "rejected_ids": [int(r["file_id"]) for r in rejected],
        "rejections": rejected,
    }
