# -*- coding: utf-8 -*-
"""排污子第11槽 · 红测丙（zheng）：两路会话同批抢结案完成态，批锁串行，后到只记争用痕。

并发脚本 ping_complete_lock 打同批写口：先到拿 sample 批锁并完成，
后到 409，仅在 contention_log 留“争用失败”，败方零完成态。
"""
from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from app import app
from db import connect, init_db


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "effluent11_zheng.db")
    init_db()
    c = TestClient(app)
    tok = c.post(
        "/api/login", json={"username": "admin", "password": "admin123"}
    ).json()["token"]
    c.headers.update({"Authorization": "Bearer " + tok})
    outfalls = c.get("/api/outfalls").json()["items"]
    outfall = next(x for x in outfalls if x["outfall_code"] == "OF-E1-A")
    sample = c.post(
        "/api/samples",
        json={
            "outfall_id": outfall["id"],
            "permit_ref": "DP-2026-E01",
            "sample_code": "SM-K11-Z",
            "flow_m3h": 2000.0,
            "metrics": {"cod": 30.0, "nh3n": 2.0, "tp": 0.2},
        },
    ).json()
    c.post("/api/releases", json={"sample_id": sample["id"]})
    c.post("/api/seals", json={"sample_id": sample["id"]})
    jobs = c.post(
        "/api/stubs/lab-courier",
        json={"sample_code": "SM-K11-Z", "courier_slot": "K11", "mode": "enqueue"},
    ).json()
    c.post(
        f"/api/stubs/lab-courier/{jobs['id']}/receipt",
        json={"receipt_no": "RC-K11-Z-001"},
    )
    return sample["id"]


def _login(user: str, password: str) -> TestClient:
    c = TestClient(app)
    tok = c.post(
        "/api/login", json={"username": user, "password": password}
    ).json()["token"]
    c.headers.update({"Authorization": "Bearer " + tok})
    return c


def test_zheng_two_sessions_contend_same_batch_complete(seeded):
    sample_id = seeded
    barrier = threading.Barrier(2)
    results: dict[str, tuple] = {}

    def hit(name: str, user: str, password: str) -> None:
        client = _login(user, password)
        barrier.wait()  # 两路会话同时打同批完成写口
        r = client.post("/api/releases/complete", json={"sample_id": sample_id})
        results[name] = (r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else {})

    t1 = threading.Thread(target=hit, args=("admin路", "admin", "admin123"))
    t2 = threading.Thread(target=hit, args=("writer路", "writer", "writer123"))
    t1.start(); t2.start()
    t1.join(); t2.join()

    statuses = sorted(code for code, _ in results.values())
    # 一成一拒
    assert statuses == [200, 409]
    winner = [n for n, v in results.items() if v[0] == 200][0]
    loser = [n for n, v in results.items() if v[0] == 409][0]
    assert results[winner][1]["status"] == "已结案"
    assert "锁" in results[loser][1]["detail"]

    with connect() as conn:
        # 正式完成态恰一条
        formal = conn.execute(
            "SELECT COUNT(*) c FROM case_complete_registry WHERE sample_id=?",
            (sample_id,),
        ).fetchone()["c"]
        assert formal == 1
        # 采样状态只被成功者推进一次
        status = conn.execute(
            "SELECT status FROM sample_batches WHERE id=?", (sample_id,)
        ).fetchone()["status"]
        assert status == "已结案"
        # 后到只记争用痕
        rows = conn.execute(
            "SELECT actor, action, detail FROM contention_log WHERE lock_key=?",
            (f"sample:{sample_id}",),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["action"] == "争用失败"
        assert rows[0]["actor"] == ("writer" if winner == "admin路" else "admin")
        assert "持有人" in rows[0]["detail"]
