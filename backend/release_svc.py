"""准排放裁定放行与结案完成写口（effluent-11 回执禁结）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit
from lab_courier_stub_svc import receipt_arrived
from locks import release, require_lock
from models import CompleteIn, ReleaseIn
from permits_svc import deduct_quota
from validators import validate_sample_releasable

router = APIRouter(tags=["release"])


@router.get("/api/releases")
def list_releases(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """SELECT r.*, s.sample_code, o.outfall_code FROM discharge_releases r
               JOIN sample_batches s ON s.id=r.sample_id
               JOIN outfalls o ON o.id=r.outfall_id
               ORDER BY r.id DESC"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.post("/api/releases")
def create_release(body: ReleaseIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    lock_key = f"sample:{body.sample_id}"
    with connect() as conn:
        require_lock(conn, lock_key, user)
        try:
            sample = conn.execute(
                "SELECT * FROM sample_batches WHERE id=?", (body.sample_id,)
            ).fetchone()
            if not sample:
                raise HTTPException(404, "采样批次不存在")
            validate_sample_releasable(sample["status"])
            open_hold = conn.execute(
                "SELECT id FROM exceed_holds WHERE sample_id=? AND status='开放'",
                (body.sample_id,),
            ).fetchone()
            if open_hold:
                raise HTTPException(400, "仍有开放超标挂起，禁止准排")
            existing = conn.execute(
                "SELECT id FROM discharge_releases WHERE sample_id=? AND status='已准排'",
                (body.sample_id,),
            ).fetchone()
            if existing:
                raise HTTPException(400, "已准排，勿重复")
            ref = f"RL-{sample['sample_code']}"
            conn.execute(
                """INSERT INTO discharge_releases(sample_id,outfall_id,release_ref,status,officer,released_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    body.sample_id,
                    sample["outfall_id"],
                    ref,
                    "已准排",
                    body.officer,
                    now_iso(),
                ),
            )
            conn.execute(
                "UPDATE sample_batches SET status=? WHERE id=?",
                ("已准排", body.sample_id),
            )
            write_audit(
                conn,
                user,
                "release",
                sample["sample_code"],
                {"release_ref": ref, "officer": body.officer},
            )
            conn.commit()
            return {"release_ref": ref, "status": "已准排"}
        finally:
            release(conn, lock_key, user)
            conn.commit()


def _formal_complete(conn, sample, user: str, receipt_no: str) -> str:
    """原子升正：正式册一条 + 采样完成态 + 配额扣减，同事务零混用。"""
    ref = f"CC-{sample['sample_code']}"
    conn.execute(
        """INSERT INTO case_complete_registry(sample_id,complete_ref,status,receipt_no,
           officer,completed_at) VALUES (?,?,?,?,?,?)""",
        (sample["id"], ref, "已结案", receipt_no, user, now_iso()),
    )
    # 乙路径旧草稿当场作废，绝不与正式完成双写
    conn.execute(
        """UPDATE shadow_case_closings SET status='草稿作废', voided_at=?
           WHERE sample_id=? AND status='待回报草稿'""",
        (now_iso(), sample["id"]),
    )
    conn.execute(
        "UPDATE sample_batches SET status='已结案' WHERE id=?",
        (sample["id"],),
    )
    # 许可配额扣减推迟到回执到达后的正式升正（许可服务留痕）
    deduct_quota(conn, sample["permit_ref"], sample["id"], float(sample["flow_m3h"]), user)
    return ref


@router.post("/api/releases/complete")
def complete_case(body: CompleteIn, authorization: AuthHeader = None):
    """排放批结案写口。

    拍板口径（当日锁死，旁门不要）：外送化验回执到达与结案完成写库两边不得混用。
    - 甲路径 formal（默认）：回执列空则正式表当场拒写，完成态零改；
    - 乙路径 shadow：无回执只许登记影子草稿，原子升正前正式区零改，
      回执到达后升正，旧草稿作废。
    """
    user = require_writer(authorization)
    if body.mode not in ("formal", "shadow"):
        raise HTTPException(400, "结案模式仅支持 formal / shadow")
    lock_key = f"sample:{body.sample_id}"
    with connect() as conn:
        require_lock(conn, lock_key, user)
        try:
            sample = conn.execute(
                "SELECT * FROM sample_batches WHERE id=?", (body.sample_id,)
            ).fetchone()
            if not sample:
                raise HTTPException(404, "采样批次不存在")
            if conn.execute(
                "SELECT id FROM case_complete_registry WHERE sample_id=?",
                (body.sample_id,),
            ).fetchone():
                raise HTTPException(400, "正式册已结案，勿重复")
            if sample["status"] != "已封批":
                raise HTTPException(400, f"未封批不可结案：{sample['status']}")

            has_receipt = receipt_arrived(conn, sample["sample_code"])

            # 乙路径：无回执只许落影子区，正式区零改
            if body.mode == "shadow" and not has_receipt:
                shadow_ref = f"SH-{sample['sample_code']}"
                conn.execute(
                    """INSERT INTO shadow_case_closings(sample_id,shadow_ref,status,
                       officer,created_at) VALUES (?,?,?,?,?)""",
                    (body.sample_id, shadow_ref, "待回报草稿", user, now_iso()),
                )
                write_audit(
                    conn,
                    user,
                    "shadow_closing",
                    sample["sample_code"],
                    {"shadow_ref": shadow_ref, "reason": "外送回执未到，只登记影子"},
                )
                conn.commit()
                return {
                    "zone": "影子",
                    "promoted": False,
                    "shadow_ref": shadow_ref,
                    "status": "待回报草稿",
                }

            # 甲路径（及乙路径回执已到的升正）：回执列空当场拒写
            if not has_receipt:
                write_audit(
                    conn,
                    user,
                    "回执禁结偏航",
                    sample["sample_code"],
                    {
                        "mode": body.mode,
                        "reason": "外送化验回执未到，结案正式表拒写，完成态零改",
                    },
                )
                conn.commit()
                raise HTTPException(400, "外送化验回执未到，禁止结案：正式册拒写")

            receipt_row = conn.execute(
                """SELECT r.receipt_no FROM lab_courier_receipts r
                   JOIN lab_courier_jobs j ON j.id=r.job_id
                   WHERE j.sample_code=? AND r.receipt_status='已签收'
                   ORDER BY r.id DESC LIMIT 1""",
                (sample["sample_code"],),
            ).fetchone()
            ref = _formal_complete(conn, sample, user, receipt_row["receipt_no"])
            write_audit(
                conn,
                user,
                "case_complete",
                sample["sample_code"],
                {"complete_ref": ref, "receipt_no": receipt_row["receipt_no"]},
            )
            conn.commit()
            return {
                "zone": "正式",
                "promoted": body.mode == "shadow",
                "complete_ref": ref,
                "status": "已结案",
                "receipt_no": receipt_row["receipt_no"],
            }
        finally:
            release(conn, lock_key, user)
            conn.commit()
