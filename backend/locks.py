"""排放批争用锁。"""
from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit

router = APIRouter(tags=["locks"])

# effluent-11：两路会话同批并发的进程内实时门闩。
# SQLite 锁表随连接/请求释放，无法表达“同时在飞”的抢占，
# 门闩与 effluent_locks 同键同语义，败方同样只记争用痕并 409。
_BATCH_GATES: dict[str, str] = {}
_BATCH_GATE_LOCK = threading.Lock()


def _contention(conn, lock_key: str, holder: str, detail: str) -> None:
    # 争用痕独立落盘：随后抛 409 会触发上下文回滚，不能让争用痕被一起回滚
    conn.execute(
        """INSERT INTO contention_log(lock_key,actor,action,detail,created_at)
           VALUES (?,?,?,?,?)""",
        (lock_key, holder, "争用失败", detail, now_iso()),
    )
    conn.commit()


def require_lock(conn, lock_key: str, holder: str) -> None:
    # 实时门闩优先：同批另一路会话仍在飞则当场 409，只记争用痕、不留残锁
    with _BATCH_GATE_LOCK:
        owner = _BATCH_GATES.get(lock_key)
        if owner and owner != holder:
            _contention(conn, lock_key, holder, f"批锁并发争用 持有人={owner}")
            raise HTTPException(409, f"锁被占用：{lock_key} 持有人 {owner}")
        _BATCH_GATES[lock_key] = holder
    row = conn.execute(
        "SELECT holder FROM effluent_locks WHERE lock_key=?", (lock_key,)
    ).fetchone()
    if row and row["holder"] != holder:
        _contention(conn, lock_key, holder, f"持有人={row['holder']}")
        raise HTTPException(409, f"锁被占用：{lock_key} 持有人 {row['holder']}")
    if not row:
        # 原子抢占：两路会话同批并发时，唯一约束保证只成一路，败路转争用痕
        try:
            conn.execute(
                "INSERT INTO effluent_locks(lock_key,holder,acquired_at) VALUES (?,?,?)",
                (lock_key, holder, now_iso()),
            )
        except Exception as exc:
            owner = conn.execute(
                "SELECT holder FROM effluent_locks WHERE lock_key=?", (lock_key,)
            ).fetchone()
            owner_name = owner["holder"] if owner else "未知"
            _contention(
                conn, lock_key, holder, f"原子抢批失败 持有人={owner_name}"
            )
            raise HTTPException(
                409, f"锁被占用：{lock_key} 持有人 {owner_name}"
            ) from exc


def release(conn, lock_key: str, holder: str) -> None:
    with _BATCH_GATE_LOCK:
        if _BATCH_GATES.get(lock_key) == holder:
            _BATCH_GATES.pop(lock_key, None)
    conn.execute(
        "DELETE FROM effluent_locks WHERE lock_key=? AND holder=?",
        (lock_key, holder),
    )


@router.get("/api/locks")
def list_locks(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        locks = [dict(r) for r in conn.execute("SELECT * FROM effluent_locks").fetchall()]
        logs = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM contention_log ORDER BY id DESC LIMIT 50"
            ).fetchall()
        ]
        return {"locks": locks, "contention": logs}


@router.post("/api/locks/acquire")
def acquire(lock_key: str, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        require_lock(conn, lock_key, user)
        write_audit(conn, user, "lock_acquire", lock_key, {})
        conn.commit()
        return {"ok": True, "lock_key": lock_key, "holder": user}


@router.post("/api/locks/release")
def release_api(lock_key: str, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        release(conn, lock_key, user)
        write_audit(conn, user, "lock_release", lock_key, {})
        conn.commit()
        return {"ok": True}
