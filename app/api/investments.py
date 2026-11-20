import json
import uuid
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, status

from app.core.database import connect
from app.core.auth import get_current_user
from app.core.exceptions import validation_error, not_found_error
from app.schemas.contract_models import (
    InvestmentConfirmRequest,
    InvestmentConfirmResponse,
    InvestmentsListResponse,
    Investment,
)
from app.services.market_data import get_context_data

router = APIRouter(prefix="/investments", tags=["Investments"])


@router.post("/confirm", status_code=status.HTTP_201_CREATED, response_model=InvestmentConfirmResponse)
def confirm_investment(req: InvestmentConfirmRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    with connect() as db:
        draft_row = db.execute(
            "SELECT * FROM investment_drafts WHERE confirm_token = ? AND user_id = ?",
            (req.confirm_token, user_id),
        ).fetchone()

        if not draft_row:
            raise not_found_error("Invalid or expired confirmation token")

        # Check expiry
        expires_at_dt = datetime.fromisoformat(draft_row["expires_at"].replace("Z", "+00:00"))
        if now > expires_at_dt:
            db.execute("DELETE FROM investment_drafts WHERE confirm_token = ?", (req.confirm_token,))
            raise validation_error("Confirmation token has expired")

        draft = json.loads(draft_row["draft"])

        # Apply overrides if provided
        ticker = (req.ticker or draft["ticker"]).upper()
        stock_name = draft.get("stock_name") or ticker
        quantity = float(req.quantity if req.quantity is not None else draft["quantity"])
        avg_price = float(req.avg_price if req.avg_price is not None else draft["avg_price"])
        purchase_date = req.purchase_date or draft["purchase_date"]
        linked_tip_id = draft.get("linked_tip_id")

        if quantity <= 0:
            raise validation_error("Quantity must be greater than 0")
        if avg_price <= 0:
            raise validation_error("Average price must be greater than 0")

        # Get current price
        ctx = get_context_data(ticker)
        current_price = ctx.get("price_now") or avg_price
        current_value = round(quantity * current_price, 2)

        inv_id = f"inv_{uuid.uuid4().hex[:8]}"

        db.execute(
            """
            INSERT INTO investments (
                id, user_id, ticker, stock_name, quantity, avg_price,
                purchase_date, current_price, current_value, linked_tip_id,
                is_demo, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                inv_id,
                user_id,
                ticker,
                stock_name,
                quantity,
                avg_price,
                purchase_date,
                current_price,
                current_value,
                linked_tip_id,
                now_iso,
            ),
        )

        # Remove the draft
        db.execute("DELETE FROM investment_drafts WHERE confirm_token = ?", (req.confirm_token,))

    return InvestmentConfirmResponse(
        investment=Investment(
            id=inv_id,
            ticker=ticker,
            stock_name=stock_name,
            quantity=quantity,
            avg_price=avg_price,
            purchase_date=purchase_date,
            current_price=current_price,
            current_value=current_value,
            linked_tip_id=linked_tip_id,
        )
    )


@router.get("", status_code=status.HTTP_200_OK, response_model=InvestmentsListResponse)
def get_investments(current_user: dict = Depends(get_current_user)):
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM investments WHERE user_id = ? ORDER BY created_at DESC",
            (current_user["id"],),
        ).fetchall()

    investments: List[Investment] = []
    for r in rows:
        investments.append(
            Investment(
                id=r["id"],
                ticker=r["ticker"],
                stock_name=r["stock_name"],
                quantity=r["quantity"],
                avg_price=r["avg_price"],
                purchase_date=r["purchase_date"],
                current_price=r["current_price"],
                current_value=r["current_value"],
                linked_tip_id=r["linked_tip_id"],
            )
        )

    return InvestmentsListResponse(investments=investments)
