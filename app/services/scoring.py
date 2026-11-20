import json
import uuid
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.database import connect
from app.services.market_data import get_price_at_dates
from app.services.seed import compute_source_stats_values

scheduler = BackgroundScheduler()


def run_scoring_job():
    """
    Evaluates each locked decision and its tip.
    Scores at 7, 30, and 90 days after tip date using TICKER.NS and ^NSEI.
    A tip 'worked' if the move in the claimed direction met the stated target;
    if no target was stated, if it beat NIFTY 50 by more than 2 percentage points at 30 days.
    Writes results to scored_tips.
    Creates alerts of the three types when an outcome is confirmed or missed.
    Recomputes source stats with shrinkage, evidence_level and label.
    """
    now = datetime.now(timezone.utc)

    with connect() as db:
        # 1. Fetch all locked decisions with their tips and sources
        rows = db.execute(
            """
            SELECT
                d.id AS decision_id,
                d.user_id,
                d.action,
                d.exit_target,
                d.timeframe_days,
                t.tip_id,
                t.ticker,
                t.direction,
                t.target_price,
                t.posted_at,
                t.source_id,
                s.display_name AS source_name
            FROM decisions d
            JOIN tips t ON d.tip_id = t.tip_id
            JOIN sources s ON t.source_id = s.source_id
            WHERE d.locked = 1
            """
        ).fetchall()

        for row in rows:
            tip_id = row["tip_id"]
            ticker = row["ticker"]
            target_price = row["target_price"] or row["exit_target"]
            posted_at_dt = datetime.fromisoformat(row["posted_at"].replace("Z", "+00:00"))
            elapsed_days = (now - posted_at_dt).days

            # Get market prices
            price_data = get_price_at_dates(ticker, posted_at_dt)
            entry_price = price_data.get("entry_price") or 500.0

            # Evaluate d7, d30, d90
            d7 = price_data.get("d7", {})
            d30 = price_data.get("d30", {})
            d90 = price_data.get("d90", {})

            # Determine whether outcome worked for each window
            def evaluate_window(w_dict, window_days):
                if elapsed_days < window_days:
                    return {"status": "pending", "return_pct": None, "benchmark_pct": None}
                ret = w_dict.get("return_pct") or 0.0
                bench = w_dict.get("benchmark_pct") or 0.0
                exit_p = w_dict.get("exit_price") or entry_price
                max_p = w_dict.get("max_price") or exit_p

                # Rule: met stated target or beat NIFTY 50 by > 2% at 30d
                if target_price and target_price > 0:
                    worked = max_p >= target_price if row["direction"] == "bullish" else max_p <= target_price
                else:
                    worked = (ret - bench) > 2.0

                return {
                    "status": "worked" if worked else "missed",
                    "return_pct": ret,
                    "benchmark_pct": bench,
                    "exit_price": exit_p,
                }

            w7 = evaluate_window(d7, 7)
            w30 = evaluate_window(d30, 30)
            w90 = evaluate_window(d90, 90)

            # Overall tip outcome based on active or final window
            active_window = w30 if elapsed_days >= 30 else (w7 if elapsed_days >= 7 else None)
            if active_window and active_window["status"] != "pending":
                hit = 1 if active_window["status"] == "worked" else 0
                outcome = active_window["status"]
                ret_pct = active_window["return_pct"]
                bench_pct = active_window["benchmark_pct"]
                excess_ret = round(ret_pct - bench_pct, 2)
                exit_price = active_window.get("exit_price", entry_price)

                db.execute(
                    """
                    INSERT OR REPLACE INTO scored_tips (
                        tip_id, outcome, entry_price, exit_price, return_pct,
                        cost_pct, benchmark_return_pct, excess_return, hit, scored_at
                    )
                    VALUES (?, ?, ?, ?, ?, 0.1, ?, ?, ?, ?)
                    """,
                    (
                        tip_id,
                        outcome,
                        entry_price,
                        exit_price,
                        ret_pct,
                        bench_pct,
                        excess_ret,
                        hit,
                        now.isoformat(),
                    ),
                )

                # Check if alert already exists for this tip and user
                existing_alert = db.execute(
                    "SELECT id FROM alerts WHERE tip_id = ? AND user_id = ?",
                    (tip_id, row["user_id"]),
                ).fetchone()

                if not existing_alert:
                    alert_type = "outcome_confirmed" if hit == 1 else "negative_outcome"
                    alert_id = f"a_{uuid.uuid4().hex[:8]}"
                    title = (
                        f"Outcome Confirmed: {ticker}"
                        if hit == 1
                        else f"Target Missed: {ticker}"
                    )
                    body = (
                        f"{ticker} met target with return {ret_pct}% vs benchmark {bench_pct}%."
                        if hit == 1
                        else f"{ticker} missed target with return {ret_pct}% vs benchmark {bench_pct}%."
                    )
                    results_json = json.dumps({"d7": w7, "d30": w30, "d90": w90})

                    db.execute(
                        """
                        INSERT INTO alerts (id, user_id, type, title, body, tip_id, source_name, results, read, is_demo, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
                        """,
                        (
                            alert_id,
                            row["user_id"],
                            alert_type,
                            title,
                            body,
                            tip_id,
                            row["source_name"],
                            results_json,
                            now.isoformat(),
                        ),
                    )

        # 2. Recompute Source Stats for all sources
        sources = db.execute("SELECT source_id FROM sources").fetchall()
        for s in sources:
            sid = s["source_id"]
            stat_row = db.execute(
                """
                SELECT COUNT(*) AS n_tips, SUM(hit) AS n_hits, AVG(excess_return) AS avg_excess
                FROM tips t
                JOIN scored_tips st ON t.tip_id = st.tip_id
                WHERE t.source_id = ?
                """,
                (sid,),
            ).fetchone()

            n_tips = stat_row["n_tips"] if stat_row else 0
            n_hits = stat_row["n_hits"] if (stat_row and stat_row["n_hits"] is not None) else 0
            avg_excess = round(stat_row["avg_excess"], 2) if (stat_row and stat_row["avg_excess"] is not None) else 0.0

            stats = compute_source_stats_values(n_tips, n_hits)

            db.execute(
                """
                INSERT OR REPLACE INTO source_stats (
                    source_id, n_tips, n_hits, raw_hit_rate, shrunk_hit_rate,
                    post_mean, ci_low, ci_high, evidence_level, avg_excess_return
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    n_tips,
                    n_hits,
                    stats["raw_hit_rate"],
                    stats["shrunk_hit_rate"],
                    stats["shrunk_hit_rate"],
                    stats["ci_low"],
                    stats["ci_high"],
                    stats["evidence_level"],
                    avg_excess,
                ),
            )


def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(
            run_scoring_job,
            "interval",
            days=1,
            id="daily_scoring_job",
            replace_existing=True,
        )
        scheduler.start()


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
