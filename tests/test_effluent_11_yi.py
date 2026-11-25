# -*- coding: utf-8 -*-
"""排污子第11槽 · 红测乙（yi）：结案只许登记影子，对账不得把影子完成当结案。

乙路径：回执未到，结案请求只能落到影子区（shadow_case_closings）；
原子升正正式区零改，否则待回报草稿作废。
对账服务把“影子完成”算作结案即判红——对账完结灯与空桩待回互斥。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import app
from db import connect, init_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "effluent11_yi.db")
    init_db()
    c = TestClient(app)
    tok = c.post(
        "/api/login", json={"username": "admin", "password": "admin123"}
    ).json()["token"]
    c.headers.update({"Authorization": "Bearer " + tok})
    return c


def _seed_pending_batch(client: TestClient, code: str = "SM-K11-Y") -> dict:
    outfalls = client.get("/api/outfalls").json()["items"]
    outfall = next(x for x in outfalls if x["outfall_code"] == "OF-E1-A")
    sample = client.post(
        "/api/samples",
        json={
            "outfall_id": outfall["id"],
            "permit_ref": "DP-2026-E01",
            "sample_code": code,
            "flow_m3h": 2000.0,
            "metrics": {"cod": 30.0, "nh3n": 2.0, "tp": 0.2},
        },
    ).json()
    client.post("/api/releases", json={"sample_id": sample["id"]})
    client.post("/api/seals", json={"sample_id": sample["id"]})
    client.post(
        "/api/stubs/lab-courier",
        json={"sample_code": code, "courier_slot": "K11", "mode": "enqueue"},
    )
    return {"sample_id": sample["id"], "sample_code": code}


def test_yi_shadow_only_when_receipt_missing(client: TestClient):
    batch = _seed_pending_batch(client)

    # 乙路径：无回执只许登记影子
    shadow = client.post(
        "/api/releases/complete",
        json={"sample_id": batch["sample_id"], "mode": "shadow"},
    )
    assert shadow.status_code == 200
    assert shadow.json()["zone"] == "影子"
    assert shadow.json()["promoted"] is False

    with connect() as conn:
        shadow_rows = conn.execute(
            "SELECT status FROM shadow_case_closings WHERE sample_id=?",
            (batch["sample_id"],),
        ).fetchall()
        assert len(shadow_rows) == 1
        assert shadow_rows[0]["status"] == "待回报草稿"
        # 正式区零改
        formal = conn.execute(
            "SELECT COUNT(*) c FROM case_complete_registry WHERE sample_id=?",
            (batch["sample_id"],),
        ).fetchone()["c"]
        assert formal == 0
        # 许可配额零扣
        deduct = conn.execute(
            "SELECT COUNT(*) c FROM permit_quota_ledger WHERE sample_id=?",
            (batch["sample_id"],),
        ).fetchone()["c"]
        assert deduct == 0
        status = conn.execute(
            "SELECT status FROM sample_batches WHERE id=?",
            (batch["sample_id"],),
        ).fetchone()["status"]
        assert status == "已封批"


def test_yi_reconcile_does_not_count_shadow_as_closed(client: TestClient):
    batch = _seed_pending_batch(client)
    client.post(
        "/api/releases/complete",
        json={"sample_id": batch["sample_id"], "mode": "shadow"},
    )

    recon = client.get("/api/reconcile/DP-2026-E01").json()

    # 对账完结灯与空桩待回互斥：存在待回外送，对账不得宣告完结
    assert recon["pending_lab_receipts"] >= 1
    assert recon["closed_complete"] is False
    assert recon["balanced_finalized"] is False
    reason = " ".join(recon.get("blockers", []))
    assert "回执" in reason
    # 影子不得被计入正式结案
    assert recon["formal_closed_count"] == 0
    assert recon["shadow_count"] >= 1


def test_yi_promote_after_receipt_voids_draft_without_promotion(client: TestClient):
    batch = _seed_pending_batch(client)
    client.post(
        "/api/releases/complete",
        json={"sample_id": batch["sample_id"], "mode": "shadow"},
    )

    # 原子升正：回执到达后走正式结案；正式区零改时草稿作废，绝不双写
    jobs = client.get("/api/stubs/lab-courier").json()["items"]
    job = next(j for j in jobs if j["sample_code"] == batch["sample_code"])
    client.post(
        f"/api/stubs/lab-courier/{job['id']}/receipt",
        json={"receipt_no": "RC-K11-Y-001"},
    )
    promoted = client.post(
        "/api/releases/complete", json={"sample_id": batch["sample_id"]}
    )
    assert promoted.status_code == 200
    assert promoted.json()["zone"] == "正式"

    with connect() as conn:
        # 影子草稿已作废，正式册恰一条，不混用
        draft = conn.execute(
            "SELECT status FROM shadow_case_closings WHERE sample_id=?",
            (batch["sample_id"],),
        ).fetchall()
        assert draft and all(r["status"] == "草稿作废" for r in draft)
        formal = conn.execute(
            "SELECT COUNT(*) c FROM case_complete_registry WHERE sample_id=?",
            (batch["sample_id"],),
        ).fetchone()["c"]
        assert formal == 1
        # 配额只在升正时扣一次
        deduct = conn.execute(
            "SELECT COUNT(*) c FROM permit_quota_ledger WHERE sample_id=?",
            (batch["sample_id"],),
        ).fetchone()["c"]
        assert deduct == 1
