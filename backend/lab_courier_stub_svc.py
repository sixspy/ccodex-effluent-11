"""空桩：外送化验快递槽（题面可点到接口，默认 dry_run）。

effluent-11 回执禁结：
- 外送化验入队后回执列默认为空（待回）；
- 回执到达只许经 /receipt 写口签收，与结案完成写库两边不得混用；
- 列表逐作业带出 receipt_status，页面“待回”与总览同态。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit
from models import LabCourierIn

router = APIRouter(tags=["lab_courier_stub"])


class ReceiptIn(BaseModel):
    receipt_no: str = Field(min_length=1, max_length=64)


def receipt_arrived(conn, sample_code: str) -> bool:
    """该采样是否存在任一“已签收”外送回执（空判只认回执列，不看结案侧）。"""
    row = conn.execute(
        """SELECT 1 FROM lab_courier_receipts r
           JOIN lab_courier_jobs j ON j.id=r.job_id
           WHERE j.sample_code=? AND r.receipt_status='已签收' LIMIT 1""",
        (sample_code,),
    ).fetchone()
    return row is not None


@router.get("/api/stubs/lab-courier")
def list_jobs(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """SELECT j.*, r.receipt_no, r.receipt_status, r.arrived_at
               FROM lab_courier_jobs j
               LEFT JOIN lab_courier_receipts r ON r.job_id=j.id
               ORDER BY j.id DESC"""
        ).fetchall()
        items = [dict(r) for r in rows]
        pending = sum(1 for x in items if not x.get("receipt_status"))
        return {
            "items": items,
            "stub": True,
            "ready": False,
            "pending_lab_receipts": pending,
        }


@router.post("/api/stubs/lab-courier")
def enqueue(body: LabCourierIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    if body.mode not in ("dry_run", "enqueue"):
        raise HTTPException(400, "仅支持 dry_run / enqueue")
    with connect() as conn:
        status = "演练" if body.mode == "dry_run" else "排队"
        cur = conn.execute(
            """INSERT INTO lab_courier_jobs(sample_code,courier_slot,mode,status,detail,created_at)
               VALUES (?,?,?,?,?,?)""",
            (
                body.sample_code,
                body.courier_slot,
                body.mode,
                status,
                body.detail or "空桩未接通外送",
                now_iso(),
            ),
        )
        write_audit(
            conn,
            user,
            "lab_courier_stub",
            body.sample_code,
            body.model_dump(),
        )
        conn.commit()
        return {
            "id": cur.lastrowid,
            "status": status,
            "stub": True,
            "receipt_status": None,
        }


@router.post("/api/stubs/lab-courier/{job_id}/receipt")
def mark_receipt(job_id: int, body: ReceiptIn, authorization: AuthHeader = None):
    """回执到达签收写口：只写空桩回执列，不触碰任何结案正式区。"""
    user = require_writer(authorization)
    with connect() as conn:
        job = conn.execute(
            "SELECT * FROM lab_courier_jobs WHERE id=?", (job_id,)
        ).fetchone()
        if not job:
            raise HTTPException(404, "外送作业不存在")
        if conn.execute(
            "SELECT id FROM lab_courier_receipts WHERE job_id=?", (job_id,)
        ).fetchone():
            raise HTTPException(400, "该作业回执已签收，勿重复")
        arrived = now_iso()
        conn.execute(
            """INSERT INTO lab_courier_receipts(job_id,sample_code,receipt_no,
               receipt_status,arrived_at) VALUES (?,?,?,?,?)""",
            (job_id, job["sample_code"], body.receipt_no, "已签收", arrived),
        )
        conn.execute(
            "UPDATE lab_courier_jobs SET status='回执已到' WHERE id=?", (job_id,)
        )
        write_audit(
            conn,
            user,
            "lab_receipt_arrive",
            job["sample_code"],
            {"job_id": job_id, "receipt_no": body.receipt_no},
        )
        conn.commit()
        return {
            "job_id": job_id,
            "sample_code": job["sample_code"],
            "receipt_no": body.receipt_no,
            "receipt_status": "已签收",
            "arrived_at": arrived,
        }
