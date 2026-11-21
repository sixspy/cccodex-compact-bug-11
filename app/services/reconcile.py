"""体积对账：对照计划挂载体积、闸检被拒件与合并结果。"""
from __future__ import annotations

from app.db import get_db
from app.services import merge_gate
from app.services.errors import ServiceError


def list_reports(db_path: str | None = None) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT r.*, p.plan_code, p.target_table FROM volume_reports r "
            "JOIN compact_plans p ON p.id=r.plan_id ORDER BY r.id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def run_reconcile(plan_id: int, db_path: str | None = None) -> dict:
    with get_db(db_path) as conn:
        plan = conn.execute(
            "SELECT * FROM compact_plans WHERE id=?", (plan_id,)
        ).fetchone()
        if not plan:
            raise ServiceError("计划不存在", 404)
        before = conn.execute(
            "SELECT COALESCE(SUM(f.size_bytes),0) AS b, COUNT(*) AS c "
            "FROM plan_items i JOIN lake_files f ON f.id=i.file_id WHERE i.plan_id=?",
            (plan_id,),
        ).fetchone()
        # 与闸检同源：被拒的低阈件不计入应合并体积。
        gate = merge_gate.summarize(plan_id, db_path)
        rejected_ids = set(int(x) for x in gate.get("rejected_ids", []))
        rejected_bytes = 0
        rejected_in_plan = 0
        if rejected_ids:
            rows = conn.execute(
                "SELECT f.id, f.size_bytes FROM plan_items i "
                "JOIN lake_files f ON f.id=i.file_id WHERE i.plan_id=?",
                (plan_id,),
            ).fetchall()
            for r in rows:
                if int(r["id"]) in rejected_ids:
                    rejected_bytes += int(r["size_bytes"])
                    rejected_in_plan += 1
        job = conn.execute(
            "SELECT * FROM rewrite_jobs WHERE plan_id=? AND status='成功' "
            "ORDER BY id DESC LIMIT 1",
            (plan_id,),
        ).fetchone()
        after = int(job["merged_bytes"]) if job else 0
        before_b = int(before["b"])
        expect_b = before_b - rejected_bytes
        summary = (
            f"计划#{plan_id} {plan['plan_code']}：挂载前 {before_b} 字节 / "
            f"{before['c']} 文件，合并后记 {after} 字节"
        )
        if rejected_in_plan:
            summary += (
                f"；闸检拒 {rejected_in_plan} 件（{rejected_bytes} 字节），"
                f"应合并 {expect_b} 字节"
            )
        if job and expect_b != after:
            summary += "；体积与闸检后预期不一致须人工核对"
        elif job:
            summary += "；体积与闸检后预期一致"
        cur = conn.execute(
            "INSERT INTO volume_reports(plan_id, before_bytes, after_bytes, file_count, summary) "
            "VALUES (?,?,?,?,?)",
            (plan_id, before_b, after, int(before["c"]), summary),
        )
        return dict(
            conn.execute(
                "SELECT * FROM volume_reports WHERE id=?", (cur.lastrowid,)
            ).fetchone()
        )
