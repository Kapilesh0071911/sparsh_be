import json
from typing import List
from fastapi import APIRouter, Depends, status

from app.core.database import connect
from app.core.auth import get_current_user
from app.core.exceptions import not_found_error
from app.schemas.contract_models import (
    AlertsListResponse,
    AlertReadResponse,
    AlertOut,
    AlertResults,
    AlertResult,
)

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("", status_code=status.HTTP_200_OK, response_model=AlertsListResponse)
def get_alerts(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]

    with connect() as db:
        unread_count = db.execute(
            "SELECT COUNT(*) FROM alerts WHERE user_id = ? AND read = 0",
            (user_id,),
        ).fetchone()[0]

        rows = db.execute(
            "SELECT * FROM alerts WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()

    alert_items: List[AlertOut] = []
    for r in rows:
        raw_res = json.loads(r["results"])
        d7 = raw_res.get("d7", {"status": "pending", "return_pct": None, "benchmark_pct": None})
        d30 = raw_res.get("d30", {"status": "pending", "return_pct": None, "benchmark_pct": None})
        d90 = raw_res.get("d90", {"status": "pending", "return_pct": None, "benchmark_pct": None})

        alert_items.append(
            AlertOut(
                id=r["id"],
                type=r["type"],
                title=r["title"],
                body=r["body"],
                tip_id=r["tip_id"],
                source_name=r["source_name"],
                results=AlertResults(
                    d7=AlertResult(
                        status=d7["status"],
                        return_pct=d7.get("return_pct"),
                        benchmark_pct=d7.get("benchmark_pct"),
                    ),
                    d30=AlertResult(
                        status=d30["status"],
                        return_pct=d30.get("return_pct"),
                        benchmark_pct=d30.get("benchmark_pct"),
                    ),
                    d90=AlertResult(
                        status=d90["status"],
                        return_pct=d90.get("return_pct"),
                        benchmark_pct=d90.get("benchmark_pct"),
                    ),
                ),
                created_at=r["created_at"],
                read=bool(r["read"]),
            )
        )

    return AlertsListResponse(unread_count=unread_count, alerts=alert_items)


@router.post("/{alert_id}/read", status_code=status.HTTP_200_OK, response_model=AlertReadResponse)
def mark_alert_read(alert_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]

    with connect() as db:
        alert = db.execute(
            "SELECT id FROM alerts WHERE id = ? AND user_id = ?",
            (alert_id, user_id),
        ).fetchone()

        if not alert:
            raise not_found_error(f"Alert {alert_id} not found")

        db.execute(
            "UPDATE alerts SET read = 1 WHERE id = ? AND user_id = ?",
            (alert_id, user_id),
        )

        unread_count = db.execute(
            "SELECT COUNT(*) FROM alerts WHERE user_id = ? AND read = 0",
            (user_id,),
        ).fetchone()[0]

    return AlertReadResponse(unread_count=unread_count)


@router.post("/read_all", status_code=status.HTTP_200_OK, response_model=AlertReadResponse)
def mark_all_alerts_read(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]

    with connect() as db:
        db.execute(
            "UPDATE alerts SET read = 1 WHERE user_id = ?",
            (user_id,),
        )

    return AlertReadResponse(unread_count=0)
