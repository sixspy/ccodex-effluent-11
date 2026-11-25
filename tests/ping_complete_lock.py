# -*- coding: utf-8 -*-
"""排污子第11槽 · 并发脚本：ping_complete_lock 打同批结案完成写口。

两路会话（admin / writer）同时对同一采样批 POST /api/releases/complete，
验收批锁：一胜一负，败方 409 且 contention_log 仅留争用痕、零完成态。

本机种子目录独立临时库，用法：
    python tests/ping_complete_lock.py
"""
from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path

from fastapi.testclient import TestClient

from app import app
from db import connect, init_db


def _auth(client: TestClient, user: str, password: str) -> None:
    tok = client.post(
        "/api/login", json={"username": user, "password": password}
    ).json()["token"]
    client.headers.update({"Authorization": "Bearer " + tok})


def _seed() -> int:
    c = TestClient(app)
    _auth(c, "admin", "admin123")
    outfall = next(
        x for x in c.get("/api/outfalls").json()["items"]
        if x["outfall_code"] == "OF-E1-A"
    )
    sample = c.post(
        "/api/samples",
        json={
            "outfall_id": outfall["id"],
            "permit_ref": "DP-2026-E01",
            "sample_code": "SM-K11-PING",
            "flow_m3h": 2000.0,
            "metrics": {"cod": 30.0, "nh3n": 2.0, "tp": 0.2},
        },
    ).json()
    c.post("/api/releases", json={"sample_id": sample["id"]})
    c.post("/api/seals", json={"sample_id": sample["id"]})
    job = c.post(
        "/api/stubs/lab-courier",
        json={
            "sample_code": "SM-K11-PING",
            "courier_slot": "K11",
            "mode": "enqueue",
        },
    ).json()
    c.post(
        f"/api/stubs/lab-courier/{job['id']}/receipt",
        json={"receipt_no": "RC-K11-PING"},
    )
    return sample["id"]


def ping_complete_lock(sample_id: int) -> dict:
    barrier = threading.Barrier(2)
    outcomes: dict[str, dict] = {}

    def drive(name: str, user: str, password: str) -> None:
        client = TestClient(app)
        _auth(client, user, password)
        barrier.wait()
        r = client.post(
            "/api/releases/complete", json={"sample_id": sample_id}
        )
        try:
            body = r.json()
        except Exception:  # pragma: no cover
            body = {}
        outcomes[name] = {"status_code": r.status_code, "body": body}

    t1 = threading.Thread(target=drive, args=("admin路", "admin", "admin123"))
    t2 = threading.Thread(target=drive, args=("writer路", "writer", "writer123"))
    t1.start(); t2.start()
    t1.join(); t2.join()

    with connect() as conn:
        formal = conn.execute(
            "SELECT COUNT(*) c FROM case_complete_registry WHERE sample_id=?",
            (sample_id,),
        ).fetchone()["c"]
        contention = [
            dict(r)
            for r in conn.execute(
                "SELECT actor, action, detail FROM contention_log "
                "WHERE lock_key=?",
                (f"sample:{sample_id}",),
            ).fetchall()
        ]
    return {
        "outcomes": outcomes,
        "formal_complete_rows": formal,
        "contention": contention,
    }


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="effluent11_ping_")) / "ping.db"
    # 本进程内把库指向临时种子目录（init_db 从本机 fixtures 播种）
    import db

    db.DB_PATH = tmp
    init_db()
    sample_id = _seed()
    report = ping_complete_lock(sample_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    codes = sorted(o["status_code"] for o in report["outcomes"].values())
    ok = codes == [200, 409] and report["formal_complete_rows"] == 1
    print("PING_COMPLETE_LOCK", "PASS" if ok else "FAIL", "db=", db.DB_PATH)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
