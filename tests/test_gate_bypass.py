"""闸失效补洞（第十一号）核验：低阈件必拦、被拒原因可读、并发不双写。"""
import threading

import pytest

from app.db import get_db
from app.services import files, merge_gate, plans, rewrite, settings
from app.services.errors import ServiceError
from app.services.gate_bypass_ledger import dashboard


def _publish(dbp, table, code):
    p = plans.create_plan(code, code, table, db_path=dbp)
    plans.attach_loose_files(p["id"], db_path=dbp)
    plans.publish_plan(p["id"], db_path=dbp)
    return p["id"]


def test_all_below_threshold_is_blocked(db):
    pid = _publish(db, "dw_users", "CP-LOW")  # 三件均 < 256KB
    with pytest.raises(ServiceError) as ei:
        rewrite.start_rewrite(pid, db_path=db)
    assert ei.value.status_code == 409
    assert "全拒" in ei.value.message
    # 无合并任务、无件被合并
    with get_db(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM rewrite_jobs WHERE plan_id=?", (pid,)
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM lake_files WHERE table_name='dw_users' "
            "AND status='已合并'"
        ).fetchone()[0] == 0


def test_mixed_rejects_low_and_merges_ok(db):
    pid = plans.create_plan("CP-MIX", "混合", "dw_payments", db_path=db)["id"]
    files.register_file(
        "lake/dw_payments/part-low.parquet", "dw_payments", 100_000, db_path=db
    )
    plans.attach_loose_files(pid, db_path=db)
    plans.publish_plan(pid, db_path=db)
    job = rewrite.start_rewrite(pid, db_path=db)
    assert job["status"] == "成功"
    assert job["rejected_count"] == 1
    assert job["merged_bytes"] == 290_000 + 305_000
    # 被拒件仍在碎件列，且能读到原因
    low = [f for f in files.list_files("dw_payments", db_path=db)
           if f["size_bytes"] == 100_000][0]
    assert low["status"] != "已合并"
    assert low["gate_status"] == "已拒"
    assert "低于阈值" in low["reject_reason"]


def test_rejection_reason_survives_in_gate_tables(db):
    pid = _publish(db, "dw_users", "CP-REASON")
    with pytest.raises(ServiceError):
        rewrite.start_rewrite(pid, db_path=db)
    rejections = merge_gate.list_rejections(pid, db_path=db)
    assert len(rejections) == 3
    assert all("低于阈值" in r["reason"] for r in rejections)
    # 凭证与台参数阈值对齐
    check = merge_gate.latest_check(pid, db_path=db)
    assert check["threshold_bytes"] == merge_gate.threshold_bytes(db)
    assert check["chip"] == merge_gate.CHIP_ALL_REJECTED


def test_chip_matches_truth_not_fake_green(db):
    pid = _publish(db, "dw_users", "CP-CHIP")
    with pytest.raises(ServiceError):
        rewrite.start_rewrite(pid, db_path=db)
    dash = dashboard(db)
    assert dash["chip"] != merge_gate.CHIP_PASS
    assert dash["truth"] != "低阈仍合"
    assert not dash["fake_green"]


def test_threshold_change_flips_gate(db):
    pid = _publish(db, "dw_users", "CP-THR")
    with pytest.raises(ServiceError):
        rewrite.start_rewrite(pid, db_path=db)
    settings.update_setting("compact_threshold_kb", "100", db_path=db)
    job = rewrite.start_rewrite(pid, db_path=db)
    assert job["status"] == "成功"
    assert job["rejected_count"] == 0


def test_concurrent_start_writes_single_credential(db):
    pid = _publish(db, "dw_payments", "CP-CONC")
    outcomes = []

    def go():
        try:
            rewrite.start_rewrite(pid, db_path=db)
            outcomes.append("ok")
        except ServiceError as exc:
            outcomes.append(exc.status_code)

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert outcomes.count("ok") == 1
    assert outcomes.count(409) == 1
    with get_db(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM gate_checks WHERE plan_id=?", (pid,)
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM rewrite_jobs WHERE plan_id=?", (pid,)
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM lake_files WHERE table_name='dw_payments' "
            "AND size_bytes < ? AND status='已合并'",
            (merge_gate.threshold_bytes(db),),
        ).fetchone()[0] == 0


def test_plan_detail_exposes_threshold_and_reason(db):
    pid = _publish(db, "dw_users", "CP-DETAIL")
    with pytest.raises(ServiceError):
        rewrite.start_rewrite(pid, db_path=db)
    detail = plans.plan_detail(pid, db_path=db)
    assert detail["gate"]["rejected_count"] == 3
    assert all(it["below_threshold"] for it in detail["items"])
    assert all(it["gate_status"] == "已拒" for it in detail["items"])


def test_truth_is_data_driven_not_echoed_from_chip(db):
    """真相看湖区有没有低阈件被合并，而不是回显芯片文案。"""
    from app.services.gate_bypass_surface import snapshot

    assert snapshot(db)["truth"] != "低阈仍合"
    # 模拟漏拦：把低阈件硬塞成已合并
    with get_db(db) as conn:
        conn.execute(
            "UPDATE lake_files SET status='已合并' "
            "WHERE table_name='dw_users' AND size_bytes < ?",
            (merge_gate.threshold_bytes(db),),
        )
    snap = snapshot(db)
    assert snap["truth"] == "低阈仍合"
    assert snap["aligned"] is False


def test_new_plan_chip_not_fake_green(db):
    """没跑过闸检的新计划不得显示「闸检已过」。"""
    p = plans.create_plan("CP-NEW", "新", "dw_users", db_path=db)
    row = [x for x in plans.list_plans(db) if x["id"] == p["id"]][0]
    assert row["gate_chip"] == merge_gate.CHIP_UNCHECKED
    assert row["gate_result"] is None

