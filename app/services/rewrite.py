"""重写合并：先过阈值闸，再按合格件执行合并任务。

闸检与合并落库在同一个 ``BEGIN IMMEDIATE`` 写事务里完成，并发启动
合并时由 SQLite 写锁串行化，不会出现双写闸检凭证互相覆盖。
"""
from __future__ import annotations

from app.db import get_db
from app.services import merge_gate
from app.services.errors import ServiceError
from app.services.merge_gate import (
    RESULT_STALE,
    GateResult,
    inspect,
    write_credentials,
)


def list_jobs(db_path: str | None = None) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT j.*, p.plan_code, p.target_table FROM rewrite_jobs j "
            "JOIN compact_plans p ON p.id=j.plan_id ORDER BY j.id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def _fail_closed(gate: GateResult, reason: str) -> GateResult:
    """闸检失准：宁可拦下也不放行。"""
    gate.result = RESULT_STALE
    gate.chip = "闸检失准"
    gate.message = reason
    gate.accepted = []
    gate.rejected = []
    return gate


def start_rewrite(plan_id: int, db_path: str | None = None) -> dict:
    """合一入口：闸检与落库同一写事务，低阈件必拒。"""
    blocked: str | None = None
    job: dict | None = None
    gate: GateResult | None = None

    with get_db(db_path, immediate=True) as conn:
        plan = conn.execute(
            "SELECT * FROM compact_plans WHERE id=?", (plan_id,)
        ).fetchone()
        if not plan:
            raise ServiceError("计划不存在", 404)
        if plan["status"] not in ("已发布", "执行中"):
            raise ServiceError("仅已发布计划可启动合并", 409)
        running = conn.execute(
            "SELECT id FROM rewrite_jobs WHERE plan_id=? AND status IN ('待执行','执行中')",
            (plan_id,),
        ).fetchone()
        if running:
            raise ServiceError("已有在途合并任务", 409)

        items = conn.execute(
            "SELECT f.* FROM plan_items i JOIN lake_files f ON f.id=i.file_id "
            "WHERE i.plan_id=? AND f.status='已入计划' ORDER BY f.id",
            (plan_id,),
        ).fetchall()
        if not items:
            raise ServiceError("计划下无可合并碎文件", 409)

        gate = inspect(plan_id, conn, items)

        # 闸检判据必须与现行台参数一致；不一致说明闸检失准，按失准拦下。
        now_kb, now_thr = merge_gate.threshold_value(conn)
        if (now_kb, now_thr) != (gate.threshold_kb, gate.threshold_bytes):
            gate = _fail_closed(
                gate, "闸检阈值与现行台参数不一致，已按失准拦下"
            )

        # 兜底复核：任何小于阈值的件都不得留在合格队列里。
        if gate.result != RESULT_STALE:
            leak = [
                int(r["id"])
                for r in gate.accepted
                if int(r["size_bytes"]) < gate.threshold_bytes
            ]
            if leak:
                gate = _fail_closed(
                    gate,
                    f"碎件 {leak} 低于阈值却漏拦，已按失准拦下",
                )

        write_credentials(conn, gate)

        if gate.result == RESULT_STALE or not gate.accepted:
            # 不在这里抛：凭证要随本次事务提交，让碎件列能读到被拒原因。
            blocked = gate.message or "闸检未放行"
        else:
            total = gate.accepted_bytes()
            job_message = gate.message
            if gate.rejected_count:
                job_message = (
                    f"{gate.message}；被拒件见闸检被拒清单"
                    f"（{gate.rejected_count} 个）"
                )
            cur = conn.execute(
                "INSERT INTO rewrite_jobs(plan_id, status, merged_bytes, message, started_at) "
                "VALUES (?, '执行中', 0, '合并进行中', datetime('now'))",
                (plan_id,),
            )
            job_id = cur.lastrowid
            conn.execute(
                "UPDATE compact_plans SET status='执行中' WHERE id=?", (plan_id,)
            )
            for row in gate.accepted:
                conn.execute(
                    "UPDATE lake_files SET status='已合并' WHERE id=?", (row["id"],)
                )
            conn.execute(
                "UPDATE rewrite_jobs SET status='成功', merged_bytes=?, message=?, "
                "finished_at=datetime('now') WHERE id=?",
                (total, job_message, job_id),
            )
            conn.execute(
                "UPDATE compact_plans SET status='已完成' WHERE id=?", (plan_id,)
            )
            job = dict(
                conn.execute(
                    "SELECT * FROM rewrite_jobs WHERE id=?", (job_id,)
                ).fetchone()
            )

    if blocked is not None or job is None:
        raise ServiceError(blocked or "闸检未放行", 409)

    summary = merge_gate.summarize(plan_id, db_path)
    gate_dict = gate.to_dict()
    job["gate"] = gate_dict
    job["gate_chip"] = gate.chip
    job["rejected_count"] = gate.rejected_count
    job["rejections"] = gate_dict["rejections"]
    job["plan_gate"] = summary
    return job


def fail_open_job(job_id: int, reason: str, db_path: str | None = None) -> dict:
    """预留：标记失败（基线测试与切口）。"""
    with get_db(db_path) as conn:
        job = conn.execute(
            "SELECT * FROM rewrite_jobs WHERE id=?", (job_id,)
        ).fetchone()
        if not job:
            raise ServiceError("任务不存在", 404)
        conn.execute(
            "UPDATE rewrite_jobs SET status='失败', message=?, finished_at=datetime('now') "
            "WHERE id=?",
            (reason or "合并失败", job_id),
        )
        return dict(
            conn.execute(
                "SELECT * FROM rewrite_jobs WHERE id=?", (job_id,)
            ).fetchone()
        )
