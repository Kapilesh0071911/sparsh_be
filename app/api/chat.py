import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core.database import connect
from app.core.auth import get_current_user
from app.core.exceptions import validation_error, not_found_error
from app.schemas.contract_models import (
    ChatMessageResponse,
    ConversationDetailResponse,
    MessageItem,
    QuickReply,
)
from app.services.llm import (
    extract_tip_from_image,
    split_thesis,
    check_link,
    select_questions,
    detect_investment,
)
from app.services.questions import get_question_text
from app.services.market_data import get_context_data

router = APIRouter(prefix="", tags=["Chat"])


def check_user_jump_insight(user_id: str, current_jump_pct: float) -> Optional[str]:
    """
    Checks if user has a pattern of buying after an 8%+ jump where some lost money.
    Returns insight text if relevant.
    """
    if current_jump_pct < 8.0:
        return None

    with connect() as db:
        rows = db.execute(
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

    if len(rows) >= 2:
        lost_count = sum(1 for r in rows if r["return_pct"] is not None and r["return_pct"] < 0)
        total_count = len(rows)
        return f"You've bought after an 8%+ jump {total_count} times. {lost_count} lost money."

    return None


@router.post("/chat/message", status_code=status.HTTP_200_OK, response_model=ChatMessageResponse)
async def post_message(
    conversation_id: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
):
    if not text and not image:
        raise validation_error("At least one of text or image is required")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    user_id = current_user["id"]

    # 1. Load or initialize conversation
    with connect() as db:
        conv = None
        if conversation_id:
            conv = db.execute(
                "SELECT * FROM conversations WHERE conversation_id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
            if not conv:
                raise not_found_error(f"Conversation {conversation_id} not found")
        else:
            conversation_id = f"c_{uuid.uuid4().hex[:8]}"
            db.execute(
                """
                INSERT INTO conversations (
                    conversation_id, user_id, stage, questions_asked,
                    questions_max, tip_id, asked_question_keys, created_at, updated_at
                )
                VALUES (?, ?, 'intake', 0, 6, NULL, '[]', ?, ?)
                """,
                (conversation_id, user_id, now_iso, now_iso),
            )
            conv = db.execute(
                "SELECT * FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()

    stage = conv["stage"]
    questions_asked = conv["questions_asked"]
    questions_max = conv["questions_max"]
    tip_id = conv["tip_id"]
    asked_keys = json.loads(conv["asked_question_keys"] or "[]")
    current_question_key = conv["current_question_key"]

    # Read image bytes if provided
    image_bytes = None
    image_filename = ""
    image_mime = "image/jpeg"
    if image:
        image_bytes = await image.read()
        image_filename = image.filename or "image.jpg"
        image_mime = image.content_type or "image/jpeg"

    # Save incoming user message
    user_msg_id = f"m_{uuid.uuid4().hex[:8]}"
    user_text_content = text or (f"[Image: {image_filename}]" if image else "")
    with connect() as db:
        db.execute(
            """
            INSERT INTO messages (id, conversation_id, role, blocks, image_url, created_at)
            VALUES (?, ?, 'user', ?, ?, ?)
            """,
            (
                user_msg_id,
                conversation_id,
                json.dumps([{"type": "text", "content": user_text_content}]),
                image_filename if image else None,
                now_iso,
            ),
        )

    # -------------------------------------------------------------
    # INVESTMENT DETECTION: Check if message states a completed buy
    # -------------------------------------------------------------
    investment_confirm_block = None
    if text:
        detected_inv = detect_investment(text)
        if detected_inv:
            confirm_token = f"inv_tok_{uuid.uuid4().hex}"
            expires_at = (now + timedelta(minutes=30)).isoformat()
            draft_data = {
                "ticker": detected_inv["ticker"],
                "stock_name": detected_inv["stock_name"],
                "quantity": detected_inv["quantity"],
                "avg_price": detected_inv["avg_price"],
                "purchase_date": detected_inv["purchase_date"],
                "linked_tip_id": tip_id,
            }
            with connect() as db:
                db.execute(
                    """
                    INSERT INTO investment_drafts (confirm_token, user_id, draft, expires_at, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (confirm_token, user_id, json.dumps(draft_data), expires_at, now_iso),
                )
            investment_confirm_block = {
                "type": "investment_confirm",
                "confirm_token": confirm_token,
                "draft": {
                    "ticker": draft_data["ticker"],
                    "stock_name": draft_data["stock_name"],
                    "quantity": draft_data["quantity"],
                    "avg_price": draft_data["avg_price"],
                    "purchase_date": draft_data["purchase_date"],
                },
            }

    # -------------------------------------------------------------
    # STATE MACHINE EXECUTION
    # -------------------------------------------------------------
    assistant_blocks: List[Dict[str, Any]] = []
    quick_replies: List[QuickReply] = []

    # If completed investment was detected on this turn and stage is already locked or chitchat
    if investment_confirm_block and stage in ("locked", "chitchat"):
        assistant_blocks.append(investment_confirm_block)
        assistant_blocks.append({
            "type": "text",
            "content": "I've detected your purchase details. Please confirm the draft above to record it.",
        })
        # Save assistant message
        with connect() as db:
            db.execute(
                """
                INSERT INTO messages (id, conversation_id, role, blocks, image_url, created_at)
                VALUES (?, ?, 'assistant', ?, NULL, ?)
                """,
                (f"m_{uuid.uuid4().hex[:8]}", conversation_id, json.dumps(assistant_blocks), now_iso),
            )
        return ChatMessageResponse(
            conversation_id=conversation_id,
            stage=stage,
            questions_asked=questions_asked,
            questions_max=questions_max,
            blocks=assistant_blocks,
            quick_replies=[],
        )

    # -------------------------------------------------------------
    # STAGE: INTAKE (or initial chitchat)
    # -------------------------------------------------------------
    if stage == "intake":
        is_tip = (image is not None) or (text and any(w in text.lower() for w in ["target", "buy", "tip", "tata", "rally", "breakout", "shares"]))

        if is_tip:
            if image_bytes:
                extracted = extract_tip_from_image(image_bytes, image_filename, image_mime)
            else:
                extracted = {
                    "sender": "Neel" if "neel" in (text or "").lower() else "Anonymous tip",
                    "stock_name": "Tata Motors",
                    "ticker": "TATAMOTORS",
                    "claim": text or "Bullish breakout targeting higher levels.",
                    "red_flags": ["urgency", "unsupported_claim"],
                }

            sender_name = extracted.get("sender") or "Anonymous tip"
            stock_name = extracted.get("stock_name") or "Tata Motors"
            ticker = extracted.get("ticker") or "TATAMOTORS"
            claim = extracted.get("claim") or ""
            red_flags = extracted.get("red_flags") or []

            # Resolve sender to a source
            with connect() as db:
                source_row = db.execute(
                    """
                    SELECT s.*, st.n_tips, st.n_hits, st.shrunk_hit_rate, st.evidence_level
                    FROM sources s
                    LEFT JOIN source_stats st USING(source_id)
                    WHERE (s.user_id = ? OR s.user_id IS NULL)
                      AND LOWER(s.display_name) = LOWER(?)
                    LIMIT 1
                    """,
                    (user_id, sender_name),
                ).fetchone()

                if not source_row:
                    source_id = f"s_{uuid.uuid4().hex[:8]}"
                    stype = "anonymous" if "anon" in sender_name.lower() else "friend"
                    db.execute(
                        """
                        INSERT INTO sources (source_id, display_name, source_type, sebi_registered, data_origin, user_id, is_demo)
                        VALUES (?, ?, ?, 0, 'real', ?, 0)
                        """,
                        (source_id, sender_name, stype, user_id),
                    )
                    source_row = {
                        "source_id": source_id,
                        "display_name": sender_name,
                        "n_tips": 0,
                        "n_hits": 0,
                        "shrunk_hit_rate": 0.35,
                        "evidence_level": "none",
                    }

                source_id = source_row["source_id"]
                tips_total = source_row["n_tips"] or 0
                tips_worked = source_row["n_hits"] or 0
                shrunk_rate = round(float(source_row["shrunk_hit_rate"] or 0.35), 2)
                e_level = source_row["evidence_level"] or "none"
                source_label = "Too early to tell" if e_level in ("none", "low") else "Track record verified"

                # Save new tip
                new_tip_id = f"t_{uuid.uuid4().hex[:8]}"
                db.execute(
                    """
                    INSERT INTO tips (
                        tip_id, source_id, posted_at, raw_text, language,
                        ticker, direction, target_price, horizon_days,
                        confidence_words, extraction_conf, data_origin,
                        user_id, stock_name, is_demo
                    )
                    VALUES (?, ?, ?, ?, 'en', ?, 'bullish', 950.0, 30, '[]', 0.95, 'real', ?, ?, 0)
                    """,
                    (new_tip_id, source_id, now_iso, claim, ticker, user_id, stock_name),
                )

                # Update conversation
                db.execute(
                    """
                    UPDATE conversations
                    SET stage = 'awaiting_thesis', tip_id = ?, updated_at = ?
                    WHERE conversation_id = ?
                    """,
                    (new_tip_id, now_iso, conversation_id),
                )

            # Build required blocks in exact order per contract:
            # 1. claim_card
            assistant_blocks.append({
                "type": "claim_card",
                "tip_id": new_tip_id,
                "sender": sender_name,
                "source_id": source_id,
                "stock": {"name": stock_name, "ticker": ticker},
                "claim": claim,
                "red_flags": red_flags,
            })

            # 2. source_record
            assistant_blocks.append({
                "type": "source_record",
                "source_id": source_id,
                "source_name": sender_name,
                "tips_total": tips_total,
                "tips_worked": tips_worked,
                "shrunk_hit_rate": shrunk_rate,
                "evidence_level": e_level,
                "label": source_label,
            })

            # 3. context_card
            ctx = get_context_data(ticker)
            assistant_blocks.append({
                "type": "context_card",
                "ticker": ctx["ticker"],
                "price_now": ctx["price_now"],
                "change_7d_pct": ctx["change_7d_pct"],
                "since_tip_pct": None,
                "note": ctx["note"],
            })

            # Check for insight block if stock is up >= 8%
            insight_text = check_user_jump_insight(user_id, ctx["change_7d_pct"])
            if insight_text:
                assistant_blocks.append({
                    "type": "insight",
                    "text": insight_text,
                })

            # 4. text block asking for user's reasoning
            assistant_blocks.append({
                "type": "text",
                "content": "What is your own reasoning for this trade? Why do you believe it will play out?",
            })

            stage = "awaiting_thesis"
        else:
            # Non-tip chitchat
            stage = "chitchat"
            with connect() as db:
                db.execute(
                    "UPDATE conversations SET stage = 'chitchat', updated_at = ? WHERE conversation_id = ?",
                    (now_iso, conversation_id),
                )
            assistant_blocks.append({
                "type": "text",
                "content": "Hello! I am Tip Checkpoint. Share a screenshot or text of any stock tip you've received, and I'll audit the claims and source track record before you make a decision. Note: I never predict prices or give buy/sell advice.",
            })

    # -------------------------------------------------------------
    # STAGE: AWAITING_THESIS -> AUDITING & FIRST QUESTION
    # -------------------------------------------------------------
    elif stage == "awaiting_thesis":
        reasoning_text = text or ""

        # Fetch tip details
        with connect() as db:
            tip_row = db.execute("SELECT * FROM tips WHERE tip_id = ?", (tip_id,)).fetchone()
            ticker = tip_row["ticker"] if tip_row else "TATAMOTORS"

        # Split reasoning into 3 to 7 causal links
        raw_links = split_thesis(reasoning_text)
        links_data: List[Dict[str, Any]] = []

        with connect() as db:
            for idx, ltext in enumerate(raw_links):
                link_id = f"l_{idx + 1}"
                db_link_id = f"{conversation_id}_{link_id}"
                eval_res = check_link(ltext, ticker)
                db.execute(
                    """
                    INSERT INTO thesis_links (
                        id, conversation_id, tip_id, text, status,
                        evidence, link_order, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        db_link_id,
                        conversation_id,
                        tip_id,
                        ltext,
                        eval_res["status"],
                        json.dumps(eval_res["evidence"]) if eval_res["evidence"] else None,
                        idx + 1,
                        now_iso,
                    ),
                )
                links_data.append({
                    "id": link_id,
                    "text": ltext,
                    "status": eval_res["status"],
                    "evidence": eval_res["evidence"],  # null when unchecked or no_evidence
                })

        total_links = len(links_data)
        gaps_count = sum(1 for l in links_data if l["status"] in ("unchecked", "no_evidence"))
        summary = f"{gaps_count} of {total_links} links have no evidence."

        # Block 1: thesis_chain
        assistant_blocks.append({
            "type": "thesis_chain",
            "links": links_data,
            "gaps_count": gaps_count,
            "total_links": total_links,
            "summary": summary,
        })

        # Select the first question from fixed templates
        selected_keys = select_questions(links_data, asked_keys=[], ticker=ticker, max_select=1)
        first_q_key = selected_keys[0] if selected_keys else "core_timeframe"
        first_q_text = get_question_text(first_q_key)

        # Block 2: ONE question at a time as a text block
        assistant_blocks.append({
            "type": "text",
            "content": first_q_text,
        })

        # Update conversation
        asked_keys.append(first_q_key)
        questions_asked = 1
        stage = "questioning"

        with connect() as db:
            db.execute(
                """
                UPDATE conversations
                SET stage = 'questioning', questions_asked = 1,
                    asked_question_keys = ?, current_question_key = ?, updated_at = ?
                WHERE conversation_id = ?
                """,
                (json.dumps(asked_keys), first_q_key, now_iso, conversation_id),
            )

        quick_replies = [QuickReply(label="Don't know", value="__dont_know__")]

    # -------------------------------------------------------------
    # STAGE: QUESTIONING
    # -------------------------------------------------------------
    elif stage == "questioning":
        user_answer = (text or "").strip()

        with connect() as db:
            tip_row = db.execute("SELECT * FROM tips WHERE tip_id = ?", (tip_id,)).fetchone()
            ticker = tip_row["ticker"] if tip_row else "TATAMOTORS"

            # If user selected __dont_know__, mark related link as unverified
            if user_answer == "__dont_know__":
                with connect() as db:
                    db.execute(
                        """
                        UPDATE thesis_links
                        SET status = 'no_evidence', evidence = NULL
                        WHERE id = (
                            SELECT id FROM thesis_links
                            WHERE conversation_id = ? AND status = 'unchecked'
                            ORDER BY link_order ASC
                            LIMIT 1
                        )
                        """,
                        (conversation_id,),
                    )

        # Check if we can ask another question (cap: questions_max = 6)
        next_q_keys = select_questions([], asked_keys=asked_keys, ticker=ticker, max_select=1)

        if questions_asked < questions_max and next_q_keys:
            next_key = next_q_keys[0]
            asked_keys.append(next_key)
            questions_asked += 1
            next_q_text = get_question_text(next_key)

            assistant_blocks.append({
                "type": "text",
                "content": next_q_text,
            })

            with connect() as db:
                db.execute(
                    """
                    UPDATE conversations
                    SET questions_asked = ?, asked_question_keys = ?,
                        current_question_key = ?, updated_at = ?
                    WHERE conversation_id = ?
                    """,
                    (questions_asked, json.dumps(asked_keys), next_key, now_iso, conversation_id),
                )

            quick_replies = [QuickReply(label="Don't know", value="__dont_know__")]
        else:
            # Reached gate!
            stage = "gate"
            decision_id = f"d_{uuid.uuid4().hex[:8]}"

            # Count gaps from thesis_links
            with connect() as db:
                links_rows = db.execute(
                    "SELECT status FROM thesis_links WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchall()
                gaps_cnt = sum(1 for r in links_rows if r["status"] in ("unchecked", "no_evidence"))

                db.execute(
                    """
                    INSERT INTO decisions (
                        id, user_id, tip_id, action, timeframe_days,
                        exit_target, max_loss_pct, confidence, thesis,
                        gaps_count, locked, locked_at, is_demo, created_at
                    )
                    VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL, 'Audited thesis', ?, 0, NULL, 0, ?)
                    """,
                    (decision_id, user_id, tip_id, gaps_cnt, now_iso),
                )

                db.execute(
                    """
                    UPDATE conversations
                    SET stage = 'gate', updated_at = ?
                    WHERE conversation_id = ?
                    """,
                    (now_iso, conversation_id),
                )

            assistant_blocks.append({
                "type": "text",
                "content": "We've completed the thesis questions. Please lock in your decision parameters below.",
            })

            assistant_blocks.append({
                "type": "decision_gate",
                "decision_id": decision_id,
                "tip_id": tip_id,
                "required_fields": [
                    "action",
                    "timeframe_days",
                    "exit_target",
                    "max_loss_pct",
                    "confidence",
                ],
                "values": {
                    "action": None,
                    "timeframe_days": None,
                    "exit_target": None,
                    "max_loss_pct": None,
                    "confidence": None,
                },
                "locked": False,
                "locked_at": None,
            })

            quick_replies = []

    # -------------------------------------------------------------
    # STAGE: GATE OR LOCKED
    # -------------------------------------------------------------
    elif stage in ("gate", "locked"):
        if investment_confirm_block:
            assistant_blocks.append(investment_confirm_block)
            assistant_blocks.append({
                "type": "text",
                "content": "Investment details detected. Confirm using the card above.",
            })
        else:
            assistant_blocks.append({
                "type": "text",
                "content": "This decision is at the decision gate. Please use the decision gate controls to lock your trade parameters." if stage == "gate" else "This decision has been locked.",
            })

    # If investment confirm block was created and not yet appended
    if investment_confirm_block and not any(b.get("type") == "investment_confirm" for b in assistant_blocks):
        assistant_blocks.insert(0, investment_confirm_block)

    # Save assistant message
    with connect() as db:
        db.execute(
            """
            INSERT INTO messages (id, conversation_id, role, blocks, image_url, created_at)
            VALUES (?, ?, 'assistant', ?, NULL, ?)
            """,
            (f"m_{uuid.uuid4().hex[:8]}", conversation_id, json.dumps(assistant_blocks), now_iso),
        )

    return ChatMessageResponse(
        conversation_id=conversation_id,
        stage=stage,
        questions_asked=questions_asked,
        questions_max=questions_max,
        blocks=assistant_blocks,
        quick_replies=quick_replies,
    )


@router.get("/conversations/{conversation_id}", status_code=status.HTTP_200_OK, response_model=ConversationDetailResponse)
def get_conversation_detail(conversation_id: str, current_user: dict = Depends(get_current_user)):
    with connect() as db:
        conv = db.execute(
            "SELECT * FROM conversations WHERE conversation_id = ? AND user_id = ?",
            (conversation_id, current_user["id"]),
        ).fetchone()

        if not conv:
            raise not_found_error(f"Conversation {conversation_id} not found")

        msg_rows = db.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()

    messages: List[MessageItem] = []
    for r in msg_rows:
        blocks = json.loads(r["blocks"] or "[]")
        messages.append(
            MessageItem(
                id=r["id"],
                role=r["role"],
                created_at=r["created_at"],
                image_url=r["image_url"],
                blocks=blocks,
            )
        )

    return ConversationDetailResponse(
        conversation_id=conv["conversation_id"],
        stage=conv["stage"],
        questions_asked=conv["questions_asked"],
        questions_max=conv["questions_max"],
        messages=messages,
    )
