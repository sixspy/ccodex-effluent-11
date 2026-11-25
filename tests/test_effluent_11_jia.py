# -*- coding: utf-8 -*-
"""排污子第11槽 · 红测甲（jia）：外送回执缺失，结案正式表当场拒写、完成态零改。

口径：化验快递回执到达与结案完成写库两边不得混用。
外送化验空桩回执列空（无“已签收”回执）时，准排服务结案键必须拒绝，
正式册 SM-K11 不得出现完成态，采样状态零改、许可配额零扣。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import app
from db import connect, init_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "effluent11_jia.db")
    init_db()
    c = TestClient(app)
    tok = c.post(
        "/api/login", json={"username": "admin", "password": "admin123"}
    ).json()["token"]
    c.headers.update({"Authorization": "Bearer " + tok})
    return c


def _seed_pending_batch(client: TestClient) -> dict:
    """预置夹具：SM-K11 已封批待结案，外送化验空桩回执缺失。"""
    outfalls = client.get("/api/outfalls").json()["items"]
    outfall = next(x for x in outfalls if x["outfall_code"] == "OF-E1-A")
    sample = client.post(
        "/api/samples",
        json={
            "outfall_id": outfall["id"],
            "permit_ref": "DP-2026-E01",
            "sample_code": "SM-K11",
            "flow_m3h": 2000.0,
            "metrics": {"cod": 30.0, "nh3n": 2.0, "tp": 0.2},
        },
    ).json()
    client.post(
        "/api/releases", json={"sample_id": sample["id"], "officer": "甲值班"}
    )
    client.post("/api/seals", json={"sample_id": sample["id"]})
    # 外送化验只入队排队，回执始终未签收 → 回执列空
    job = client.post(
        "/api/stubs/lab-courier",
        json={
            "sample_code": "SM-K11",
            "courier_slot": "K11",
            "mode": "enqueue",
        },
    ).json()
    return {"sample_id": sample["id"], "job_id": job["id"]}


def test_jia_missing_receipt_rejects_formal_complete(client: TestClient):
    batch = _seed_pending_batch(client)

    refused = client.post(
        "/api/releases/complete", json={"sample_id": batch["sample_id"]}
    )

    # 当场拒写
    assert refused.status_code == 400
    assert "回执" in refused.json()["detail"]

    with connect() as conn:
        # 正式册零完成态
        formal = conn.execute(
            "SELECT COUNT(*) c FROM case_complete_registry WHERE sample_id=?",
            (batch["sample_id"],),
        ).fetchone()["c"]
        assert formal == 0
        # 采样状态零改，仍停在已封批，没有被写成已结案
        status = conn.execute(
            "SELECT status FROM sample_batches WHERE id=?",
            (batch["sample_id"],),
        ).fetchone()["status"]
        assert status == "已封批"
        # 许可配额零扣
        deduct = conn.execute(
            "SELECT COUNT(*) c FROM permit_quota_ledger WHERE sample_id=?",
            (batch["sample_id"],),
        ).fetchone()["c"]
        assert deduct == 0
        # 拒写必须留痕：回执禁结偏航
        yaw = conn.execute(
            "SELECT COUNT(*) c FROM audit_trail WHERE action='回执禁结偏航'"
        ).fetchone()["c"]
        assert yaw >= 1


def test_jia_receipt_arrived_allows_formal_complete(client: TestClient):
    batch = _seed_pending_batch(client)

    # 回执到达后才准写正式完成
    marked = client.post(
        f"/api/stubs/lab-courier/{batch['job_id']}/receipt",
        json={"receipt_no": "RC-K11-001"},
    )
    assert marked.status_code == 200
    assert marked.json()["receipt_status"] == "已签收"

    ok = client.post(
        "/api/releases/complete", json={"sample_id": batch["sample_id"]}
    )
    assert ok.status_code == 200
    assert ok.json()["zone"] == "正式"
    assert ok.json()["status"] == "已结案"

    with connect() as conn:
        formal = conn.execute(
            "SELECT COUNT(*) c FROM case_complete_registry WHERE sample_id=?",
            (batch["sample_id"],),
        ).fetchone()["c"]
        assert formal == 1
        status = conn.execute(
            "SELECT status FROM sample_batches WHERE id=?",
            (batch["sample_id"],),
        ).fetchone()["status"]
        assert status == "已结案"
