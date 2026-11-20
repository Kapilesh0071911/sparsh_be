from datetime import datetime, timezone
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, status

from app.core.database import connect
from app.core.auth import get_current_user
from app.core.exceptions import gate_incomplete_error, not_found_error
from app.schemas.contract_models import (
    DecisionLockRequest,
    DecisionLockResponse,
    DecisionsListResponse,
    Decision,
    DecisionWithStock,
    StockRef,
)

router = APIRouter(prefix="/decisions", tags=["Decisions"])


@router.post("/lock", status_code=status.HTTP_200_OK, response_model=DecisionLockResponse)
def lock_decision(req: DecisionLockRequest, current_user: dict = Depends(get_current_user)):
    missing_fields: List[str] = []

    if not req.decision_id:
        missing_fields.append("decision_id")

    if not req.action or req.action not in ("bought", "skipped", "watching"):
        missing_fields.append("action")

    if req.timeframe_days is None:
        missing_fields.append("timeframe_days")
    else:
        try:
            tf = int(req.timeframe_days)
            if tf <= 0 or float(req.timeframe_days) != tf:
                missing_fields.append("timeframe_days")
        except (ValueError, TypeError):
            missing_fields.append("timeframe_days")

    if req.exit_target is None:
        missing_fields.append("exit_target")
    else:
        try:
            target = float(req.exit_target)
            if target <= 0:
                missing_fields.append("exit_target")
        except (ValueError, TypeError):
            missing_fields.append("exit_target")

    if req.max_loss_pct is None:
        missing_fields.append("max_loss_pct")
    else:
        try:
            loss = float(req.max_loss_pct)
            if loss <= 0 or loss > 100:
                missing_fields.append("max_loss_pct")
        except (ValueError, TypeError):
            missing_fields.append("max_loss_pct")

    if req.confidence is None:
        missing_fields.append("confidence")
    else:
        try:
            conf = int(req.confidence)
            if conf < 1 or conf > 5:
                missing_fields.append("confidence")
        except (ValueError, TypeError):
            missing_fields.append("confidence")

    if missing_fields:
        # Deduplicate while preserving order
        unique_missing = list(dict.fromkeys(missing_fields))
        raise gate_incomplete_error(unique_missing)

    now = datetime.now(timezone.utc).isoformat()

    with connect() as db:
        dec = db.execute(
            "SELECT * FROM decisions WHERE id = ? AND user_id = ?",
            (req.decision_id, current_user["id"]),
        ).fetchone()

        if not dec:
            raise not_found_error(f"Decision {req.decision_id} not found")

        db.execute(
            """
            UPDATE decisions
            SET action = ?, timeframe_days = ?, exit_target = ?, max_loss_pct = ?,
                confidence = ?, locked = 1, locked_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                req.action,
                int(req.timeframe_days),
                float(req.exit_target),
                float(req.max_loss_pct),
                int(req.confidence),
                now,
                req.decision_id,
                current_user["id"],
            ),
        )

        # Update linked conversation stage to locked if exists
        db.execute(
            """
            UPDATE conversations
            SET stage = 'locked', updated_at = ?
            WHERE tip_id = ? AND user_id = ?
            """,
            (now, dec["tip_id"], current_user["id"]),
        )

        updated = db.execute(
            "SELECT * FROM decisions WHERE id = ?",
            (req.decision_id,),
        ).fetchone()

    return DecisionLockResponse(
        decision=Decision(
            id=updated["id"],
            tip_id=updated["tip_id"],
            action=updated["action"],
            timeframe_days=updated["timeframe_days"],
            exit_target=updated["exit_target"],
            max_loss_pct=updated["max_loss_pct"],
            confidence=updated["confidence"],
            thesis=updated["thesis"],
            gaps_count=updated["gaps_count"],
            locked_at=updated["locked_at"],
        )
    )


@router.get("", status_code=status.HTTP_200_OK, response_model=DecisionsListResponse)
def get_decisions(current_user: dict = Depends(get_current_user)):
    with connect() as db:
        rows = db.execute(
            """
            SELECT
                d.*,
                t.ticker,
                COALESCE(t.stock_name, t.ticker) AS stock_name,
                COALESCE(s.display_name, 'Unknown') AS source_name
            FROM decisions d
            LEFT JOIN tips t ON d.tip_id = t.tip_id
            LEFT JOIN sources s ON t.source_id = s.source_id
            WHERE d.user_id = ?
            ORDER BY d.created_at DESC
            """,
            (current_user["id"],),
        ).fetchall()

    result = []
    for r in rows:
        result.append(
            DecisionWithStock(
                id=r["id"],
                tip_id=r["tip_id"],
                action=r["action"] or "watching",
                timeframe_days=r["timeframe_days"] or 30,
                exit_target=r["exit_target"] or 0.0,
                max_loss_pct=r["max_loss_pct"] or 0.0,
                confidence=r["confidence"] or 3,
                thesis=r["thesis"],
                gaps_count=r["gaps_count"] or 0,
                locked_at=r["locked_at"],
                stock=StockRef(name=r["stock_name"], ticker=r["ticker"] or "UNKNOWN"),
                source_name=r["source_name"],
            )
        )

    return DecisionsListResponse(decisions=result)
