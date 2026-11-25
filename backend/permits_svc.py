"""排放许可册。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit
from models import PermitIn

router = APIRouter(tags=["permits"])


def deduct_quota(
    conn, permit_code: str, sample_id: int, flow_m3h: float, officer: str
) -> None:
    """effluent-11：配额扣减只在回执到达、正式升正的同事务内发生。

    无回执的影子草稿永不扣减；UNIQUE(sample_id) 保证同批只扣一次。
    """
    permit = conn.execute(
        "SELECT id FROM discharge_permits WHERE permit_code=?", (permit_code,)
    ).fetchone()
    if not permit:
        raise HTTPException(400, f"许可不存在，无法扣配额：{permit_code}")
    conn.execute(
        """INSERT INTO permit_quota_ledger(permit_code,sample_id,flow_m3h,officer,deducted_at)
           VALUES (?,?,?,?,?)""",
        (permit_code, sample_id, flow_m3h, officer, now_iso()),
    )
    write_audit(
        conn,
        officer,
        "permit_quota_deduct",
        permit_code,
        {"sample_id": sample_id, "flow_m3h": flow_m3h},
    )


@router.get("/api/permits")
def list_permits(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """SELECT d.*, p.plant_code, p.name plant_name FROM discharge_permits d
               JOIN plants p ON p.id=d.plant_id ORDER BY d.id"""
        ).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            d["quota_deducted"] = conn.execute(
                "SELECT COUNT(*) c FROM permit_quota_ledger WHERE permit_code=?",
                (d["permit_code"],),
            ).fetchone()["c"]
            items.append(d)
        return {"items": items}


@router.get("/api/permits/{permit_code}")
def get_permit(permit_code: str, authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        row = conn.execute(
            """SELECT d.*, p.plant_code FROM discharge_permits d
               JOIN plants p ON p.id=d.plant_id WHERE d.permit_code=?""",
            (permit_code,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "许可不存在")
        samples = conn.execute(
            """SELECT sample_code, status, flow_m3h, metrics FROM sample_batches
               WHERE permit_ref=? ORDER BY id DESC""",
            (permit_code,),
        ).fetchall()
        import json

        items = []
        for s in samples:
            d = dict(s)
            d["metrics"] = json.loads(d["metrics"] or "{}")
            items.append(d)
        return {"permit": dict(row), "samples": items}


@router.post("/api/permits")
def create_permit(body: PermitIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        plant = conn.execute(
            "SELECT id FROM plants WHERE id=?", (body.plant_id,)
        ).fetchone()
        if not plant:
            raise HTTPException(404, "处理厂不存在")
        if conn.execute(
            "SELECT id FROM discharge_permits WHERE permit_code=?", (body.permit_code,)
        ).fetchone():
            raise HTTPException(400, "许可编码已存在")
        cur = conn.execute(
            """INSERT INTO discharge_permits(permit_code,plant_id,quota_m3d,cod_cap,nh3n_cap,
               tp_cap,period_label,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                body.permit_code,
                body.plant_id,
                body.quota_m3d,
                body.cod_cap,
                body.nh3n_cap,
                body.tp_cap,
                body.period_label,
                "有效",
                now_iso(),
            ),
        )
        write_audit(conn, user, "permit_create", body.permit_code, body.model_dump())
        conn.commit()
        return {"id": cur.lastrowid, **body.model_dump(), "status": "有效"}
