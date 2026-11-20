from typing import List
from fastapi import APIRouter, Depends, status

from app.core.database import connect
from app.core.auth import get_current_user
from app.schemas.contract_models import InsightsListResponse, InsightItem

router = APIRouter(prefix="/insights", tags=["Insights"])


@router.get("", status_code=status.HTTP_200_OK, response_model=InsightsListResponse)
def get_insights(current_user: dict = Depends(get_current_user)):
    insights: List[InsightItem] = []
    user_id = current_user["id"]

    with connect() as db:
        # Insight 1: Bought after 8%+ jump
        jump_decisions = db.execute(
            """
            SELECT d.id, st.return_pct, st.excess_return
            FROM decisions d
            JOIN tips t ON d.tip_id = t.tip_id
            LEFT JOIN scored_tips st ON t.tip_id = st.tip_id
            WHERE d.user_id = ? AND d.action = 'bought' AND d.locked = 1
              AND (d.thesis LIKE '%jump%' OR d.thesis LIKE '%8%')
            """,
            (user_id,),
        ).fetchall()

        if len(jump_decisions) >= 2:
            total_cnt = len(jump_decisions)
            lost_cnt = sum(1 for r in jump_decisions if r["return_pct"] is not None and r["return_pct"] < 0)
            insights.append(
                InsightItem(
                    id="i_jump_loss",
                    text=f"You've bought after an 8%+ jump {total_cnt} times. {lost_cnt} lost money.",
                    evidence_count=total_cnt,
                )
            )

        # Insight 2: Personal source track record observation
        source_records = db.execute(
            """
            SELECT s.display_name, st.n_tips, st.n_hits
            FROM sources s
            JOIN source_stats st USING(source_id)
            WHERE s.user_id = ? AND st.n_tips >= 3
            """,
            (user_id,),
        ).fetchall()

        for sr in source_records:
            missed = sr["n_tips"] - sr["n_hits"]
            if missed >= 2:
                insights.append(
                    InsightItem(
                        id=f"i_src_{sr['display_name'].lower().replace(' ', '_')}",
                        text=f"{missed} of {sr['n_tips']} tips from {sr['display_name']} failed to meet their targets.",
                        evidence_count=sr["n_tips"],
                    )
                )

    return InsightsListResponse(insights=insights)
