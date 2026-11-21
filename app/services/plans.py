"""压实计划：创建、发布、挂文件，并回读闸检凭证。"""
from __future__ import annotations

from app.db import get_db
from app.services import merge_gate
from app.services.errors import ServiceError


def list_plans(db_path: str | None = None) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT p.*, "
            "(SELECT COUNT(*) FROM plan_items i WHERE i.plan_id=p.id) AS item_count, "
            "(SELECT COALESCE(SUM(f.size_bytes),0) FROM plan_items i "
            " JOIN lake_files f ON f.id=i.file_id WHERE i.plan_id=p.id) AS plan_bytes, "
            "(SELECT g.chip FROM gate_checks g WHERE g.plan_id=p.id "
            " ORDER BY g.id DESC LIMIT 1) AS gate_chip, "
            "(SELECT g.result FROM gate_checks g WHERE g.plan_id=p.id "
            " ORDER BY g.id DESC LIMIT 1) AS gate_result, "
            "(SELECT g.threshold_kb FROM gate_checks g WHERE g.plan_id=p.id "
            " ORDER BY g.id DESC LIMIT 1) AS gate_threshold_kb, "
            "(SELECT COUNT(*) FROM gate_rejections r WHERE r.plan_id=p.id "
            " AND r.gate_id=(SELECT MAX(g2.id) FROM gate_checks g2 "
            " WHERE g2.plan_id=p.id)) AS gate_rejected_count "
            "FROM compact_plans p ORDER BY p.id"
        ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            if not item.get("gate_chip"):
                item["gate_chip"] = merge_gate.CHIP_UNCHECKED
            if item["gate_rejected_count"] is None:
                item["gate_rejected_count"] = 0
            out.append(item)
        return out


def create_plan(
    plan_code: str,
    title: str,
    target_table: str,
    note: str = "",
    db_path: str | None = None,
) -> dict:
    plan_code = (plan_code or "").strip()
    title = (title or "").strip()
    target_table = (target_table or "").strip()
    if not plan_code or not title or not target_table:
        raise ServiceError("计划编号、标题、目标表必填")
    with get_db(db_path) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO compact_plans(plan_code, title, status, target_table, note) "
                "VALUES (?,?, '草稿', ?, ?)",
                (plan_code, title, target_table, note or ""),
            )
        except Exception as exc:
            raise ServiceError(f"创建计划失败：{exc}") from exc
        return dict(
            conn.execute(
                "SELECT * FROM compact_plans WHERE id=?", (cur.lastrowid,)
            ).fetchone()
        )


def attach_loose_files(plan_id: int, db_path: str | None = None) -> dict:
    with get_db(db_path) as conn:
        plan = conn.execute(
            "SELECT * FROM compact_plans WHERE id=?", (plan_id,)
        ).fetchone()
        if not plan:
            raise ServiceError("计划不存在", 404)
        if plan["status"] not in ("草稿", "已发布"):
            raise ServiceError("当前计划状态不可挂文件", 409)
        loose = conn.execute(
            "SELECT id FROM lake_files WHERE table_name=? AND status='碎文件'",
            (plan["target_table"],),
        ).fetchall()
        attached = 0
        for row in loose:
            exists = conn.execute(
                "SELECT 1 FROM plan_items WHERE plan_id=? AND file_id=?",
                (plan_id, row["id"]),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                "INSERT INTO plan_items(plan_id, file_id) VALUES (?,?)",
                (plan_id, row["id"]),
            )
            conn.execute(
                "UPDATE lake_files SET status='已入计划' WHERE id=?",
                (row["id"],),
            )
            attached += 1
        return {"plan_id": plan_id, "attached": attached}


def publish_plan(plan_id: int, db_path: str | None = None) -> dict:
    with get_db(db_path) as conn:
        plan = conn.execute(
            "SELECT * FROM compact_plans WHERE id=?", (plan_id,)
        ).fetchone()
        if not plan:
            raise ServiceError("计划不存在", 404)
        if plan["status"] != "草稿":
            raise ServiceError("仅草稿可发布", 409)
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM plan_items WHERE plan_id=?", (plan_id,)
        ).fetchone()["c"]
        if n <= 0:
            raise ServiceError("空计划不可发布", 409)
        conn.execute(
            "UPDATE compact_plans SET status='已发布' WHERE id=?", (plan_id,)
        )
        return dict(
            conn.execute(
                "SELECT * FROM compact_plans WHERE id=?", (plan_id,)
            ).fetchone()
        )


def plan_detail(plan_id: int, db_path: str | None = None) -> dict:
    with get_db(db_path) as conn:
        plan = conn.execute(
            "SELECT * FROM compact_plans WHERE id=?", (plan_id,)
        ).fetchone()
        if not plan:
            raise ServiceError("计划不存在", 404)
        items = conn.execute(
            "SELECT f.* FROM plan_items i JOIN lake_files f ON f.id=i.file_id "
            "WHERE i.plan_id=? ORDER BY f.id",
            (plan_id,),
        ).fetchall()
        gate = merge_gate.summarize(plan_id, db_path)
        kb, thr = gate["threshold_kb"], gate["threshold_bytes"]
        rejected = {
            int(r["file_id"]): r for r in gate.get("rejections", [])
        }
        out_items = []
        for row in items:
            item = dict(row)
            item["threshold_kb"] = kb
            item["threshold_bytes"] = thr
            item["below_threshold"] = int(item["size_bytes"]) < thr
            hit = rejected.get(int(item["id"]))
            if hit:
                item["gate_status"] = "已拒"
                item["reject_reason"] = hit["reason"]
            elif item["below_threshold"]:
                item["gate_status"] = "低于阈值"
                item["reject_reason"] = (
                    f"低于阈值：{item['size_bytes']} 字节 < {thr} 字节"
                )
            else:
                item["gate_status"] = "合格"
                item["reject_reason"] = ""
            out_items.append(item)
        return {
            "plan": dict(plan),
            "items": out_items,
            "gate": gate,
        }
