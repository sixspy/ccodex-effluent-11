"""排放许可与采样对账证明。"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user
from validators import validate_permit_match

router = APIRouter(tags=["reconcile"])


@router.get("/api/reconcile")
def reconcile_all(authorization: AuthHeader = None):
    require_user(authorization)
    from db import connect

    with connect() as conn:
        rows = conn.execute(
            "SELECT permit_code FROM discharge_permits ORDER BY permit_code"
        ).fetchall()
        return {"items": [_reconcile_permit(conn, r["permit_code"]) for r in rows]}


@router.get("/api/reconcile/{permit_code}")
def reconcile_one(permit_code: str, authorization: AuthHeader = None):
    require_user(authorization)
    from db import connect

    with connect() as conn:
        if not conn.execute(
            "SELECT id FROM discharge_permits WHERE permit_code=?", (permit_code,)
        ).fetchone():
            raise HTTPException(404, "许可不存在")
        return _reconcile_permit(conn, permit_code)


def _reconcile_permit(conn, permit_code: str) -> dict:
    permit = conn.execute(
        "SELECT * FROM discharge_permits WHERE permit_code=?", (permit_code,)
    ).fetchone()
    samples = conn.execute(
        """SELECT sample_code, flow_m3h, metrics, status, generation FROM sample_batches
           WHERE permit_ref=? AND status NOT IN ('作废')""",
        (permit_code,),
    ).fetchall()
    if not samples:
        return {
            "permit_code": permit_code,
            "balanced": False,
            "reason": "无采样批次",
            "samples": [],
        }
    caps = {
        "cod": permit["cod_cap"],
        "nh3n": permit["nh3n_cap"],
        "tp": permit["tp_cap"],
    }
    details = []
    all_ok = True
    for s in samples:
        metrics = json.loads(s["metrics"] or "{}")
        ok = validate_permit_match(
            caps, metrics, float(s["flow_m3h"]), float(permit["quota_m3d"])
        )
        if not ok:
            all_ok = False
        details.append(
            {
                "sample_code": s["sample_code"],
                "status": s["status"],
                "generation": s["generation"],
                "metrics": metrics,
                "flow_m3h": s["flow_m3h"],
                "matched": ok,
            }
        )
    seal_rows = conn.execute(
        """SELECT d.seal_ref, d.sample_generation, s.sample_code
           FROM discharge_seals d JOIN sample_batches s ON s.id=d.sample_id
           WHERE s.permit_ref=?""",
        (permit_code,),
    ).fetchall()

    # effluent-11：空桩待回口径——本许可下已入外送但回执列空的采样（去重）
    pending_rows = conn.execute(
        """SELECT DISTINCT j.sample_code FROM lab_courier_jobs j
           JOIN sample_batches s ON s.sample_code=j.sample_code
           LEFT JOIN lab_courier_receipts r ON r.job_id=j.id
           WHERE s.permit_ref=? AND r.id IS NULL""",
        (permit_code,),
    ).fetchall()
    pending_codes = [r["sample_code"] for r in pending_rows]
    # 影子区：无回执登记的待回报草稿，对账不得当结案
    shadow_rows = conn.execute(
        """SELECT sh.shadow_ref, sh.status, s.sample_code FROM shadow_case_closings sh
           JOIN sample_batches s ON s.id=sh.sample_id
           WHERE s.permit_ref=?""",
        (permit_code,),
    ).fetchall()
    shadow_live = [dict(x) for x in shadow_rows if x["status"] == "待回报草稿"]
    # 正式结案只认真式册
    formal_closed = conn.execute(
        """SELECT COUNT(*) c FROM case_complete_registry cr
           JOIN sample_batches s ON s.id=cr.sample_id
           WHERE s.permit_ref=? AND cr.status='已结案'""",
        (permit_code,),
    ).fetchone()["c"]
    quota_deducted = conn.execute(
        "SELECT COUNT(*) c FROM permit_quota_ledger WHERE permit_code=?",
        (permit_code,),
    ).fetchone()["c"]

    blockers = []
    if pending_codes:
        blockers.append(
            "外送化验回执未到（空桩待回）：" + "、".join(pending_codes)
        )
    if shadow_live:
        blockers.append("存在影子待回报草稿，未原子升正，不得结案")
    # 对账完结灯与空桩待回互斥：有待回/影子即不得宣告完结
    closed_complete = not blockers
    balanced_finalized = all_ok and closed_complete

    return {
        "permit_code": permit_code,
        "quota_m3d": permit["quota_m3d"],
        "caps": caps,
        "balanced": all_ok,
        "proof_ready": all_ok and len(seal_rows) >= 1,
        "seal_count": len(seal_rows),
        "samples": details,
        "seals": [dict(x) for x in seal_rows],
        # effluent-11 回执禁结口径
        "pending_lab_receipts": len(pending_codes),
        "pending_codes": pending_codes,
        "shadow_count": len(shadow_live),
        "shadows": shadow_live,
        "formal_closed_count": formal_closed,
        "quota_deducted": quota_deducted,
        "closed_complete": closed_complete,
        "balanced_finalized": balanced_finalized,
        "blockers": blockers,
    }


@router.get("/api/proof/sample/{sample_code}")
def proof_sample(sample_code: str, authorization: AuthHeader = None):
    require_user(authorization)
    from db import connect

    with connect() as conn:
        sample = conn.execute(
            "SELECT * FROM sample_batches WHERE sample_code=?", (sample_code,)
        ).fetchone()
        if not sample:
            raise HTTPException(404, "采样不存在")
        holds = conn.execute(
            "SELECT * FROM exceed_holds WHERE sample_id=?", (sample["id"],)
        ).fetchall()
        releases = conn.execute(
            "SELECT * FROM discharge_releases WHERE sample_id=?", (sample["id"],)
        ).fetchall()
        seals = conn.execute(
            "SELECT * FROM discharge_seals WHERE sample_id=?", (sample["id"],)
        ).fetchall()
        open_holds = [h for h in holds if h["status"] == "开放"]
        closed = [h for h in holds if h["status"] == "已关闭"]
        return {
            "sample_code": sample_code,
            "status": sample["status"],
            "generation": sample["generation"],
            "released": any(r["status"] == "已准排" for r in releases),
            "sealed": any(s["status"] == "已封批" for s in seals),
            "exceed_closed": len(open_holds) == 0 and (len(closed) > 0 or sample["status"] != "旁路挂起"),
            "holds": [dict(h) for h in holds],
            "releases": [dict(r) for r in releases],
            "seals": [dict(s) for s in seals],
        }
