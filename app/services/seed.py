import json
from datetime import datetime, timedelta, timezone
from app.core.database import connect
from app.core.auth import hash_password


def compute_source_stats_values(n_tips: int, n_hits: int):
    raw_hit_rate = round(n_hits / n_tips, 2) if n_tips > 0 else 0.0
    # Shrinkage: prior mean = 0.35, weight M = 5
    shrunk_hit_rate = round((n_hits + 5.0 * 0.35) / (n_tips + 5.0), 2)

    # Sample size evidence level
    # 0 none, 1 to 4 low, 5 to 14 medium, 15+ high
    if n_tips == 0:
        evidence_level = "none"
    elif n_tips <= 4:
        evidence_level = "low"
    elif n_tips <= 14:
        evidence_level = "medium"
    else:
        evidence_level = "high"

    # The label is "Too early to tell" whenever evidence_level is none or low.
    label = "Too early to tell" if evidence_level in ("none", "low") else "Track record verified"

    # Approximate 90% confidence interval
    margin = round(1.645 * ((shrunk_hit_rate * (1 - shrunk_hit_rate) + 0.01) / (n_tips + 4)) ** 0.5, 2)
    ci_low = max(0.0, round(shrunk_hit_rate - margin, 2))
    ci_high = min(1.0, round(shrunk_hit_rate + margin, 2))

    return {
        "n_tips": n_tips,
        "n_hits": n_hits,
        "raw_hit_rate": raw_hit_rate,
        "shrunk_hit_rate": shrunk_hit_rate,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "evidence_level": evidence_level,
        "label": label,
    }


def seed_demo_data():
    """
    Idempotent seed data on startup:
    demo user demo@signalnoise.app / demo1234
    personal sources Neel (4 tips, 1 worked), Kushal (3 tips, 2 worked), and 5 anonymous tips (1 worked),
    with scored outcomes, past decisions (including four bought after an 8%+ jump, three of which lost),
    and 3 alerts of different types.
    Mark seeded rows with is_demo = 1.
    """
    with connect() as db:
        user_row = db.execute(
            "SELECT id FROM users WHERE email = ?",
            ("demo@signalnoise.app",),
        ).fetchone()

        if user_row:
            return  # Already seeded

        now = datetime.now(timezone.utc)
        demo_user_id = "u_demo"
        created_time = (now - timedelta(days=60)).isoformat()

        # 1. Create Demo User
        db.execute(
            """
            INSERT OR REPLACE INTO users (id, name, email, password_hash, is_demo, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (
                demo_user_id,
                "Demo User",
                "demo@signalnoise.app",
                hash_password("demo1234"),
                created_time,
            ),
        )

        # 2. Personal Sources
        # Neel: 4 tips, 1 worked -> shrunk_hit_rate 0.31, evidence_level low, label "Too early to tell"
        neel_id = "s_neel"
        db.execute(
            """
            INSERT OR REPLACE INTO sources (source_id, display_name, source_type, sebi_registered, data_origin, user_id, is_demo)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (neel_id, "Neel", "friend", 0, "real", demo_user_id),
        )

        # Kushal: 3 tips, 2 worked
        kushal_id = "s_kushal"
        db.execute(
            """
            INSERT OR REPLACE INTO sources (source_id, display_name, source_type, sebi_registered, data_origin, user_id, is_demo)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (kushal_id, "Kushal", "friend", 0, "real", demo_user_id),
        )

        # Anonymous Tip Source: 5 tips, 1 worked
        anon_id = "s_anon"
        db.execute(
            """
            INSERT OR REPLACE INTO sources (source_id, display_name, source_type, sebi_registered, data_origin, user_id, is_demo)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (anon_id, "Anonymous tip", "anonymous", 0, "real", demo_user_id),
        )

        # 3. Tips and Scored Tips
        # Neel's tips (4 tips, 1 worked)
        neel_tips = [
            ("t_neel_1", "TATAMOTORS", "Tata Motors", 950.0, 30, (now - timedelta(days=35)).isoformat(), 1, 812.4, 960.0, 18.2, 3.5, 14.7),
            ("t_neel_2", "TCS", "Tata Consultancy Services", 4200.0, 30, (now - timedelta(days=40)).isoformat(), 0, 3950.0, 3780.0, -4.3, 1.2, -5.5),
            ("t_neel_3", "INFY", "Infosys", 1950.0, 30, (now - timedelta(days=45)).isoformat(), 0, 1820.0, 1780.0, -2.2, 2.0, -4.2),
            ("t_neel_4", "WIPRO", "Wipro", 560.0, 30, (now - timedelta(days=50)).isoformat(), 0, 510.0, 480.0, -5.9, -0.5, -5.4),
        ]

        for tip_id, ticker, stock_name, target, horizon, posted_at, hit, entry_p, exit_p, ret_p, bench_p, excess_p in neel_tips:
            db.execute(
                """
                INSERT OR REPLACE INTO tips (tip_id, source_id, posted_at, raw_text, language, ticker, direction, target_price, horizon_days, confidence_words, extraction_conf, data_origin, user_id, stock_name, is_demo)
                VALUES (?, ?, ?, ?, 'en', ?, 'bullish', ?, ?, '["breakout"]', 0.95, 'real', ?, ?, 1)
                """,
                (tip_id, neel_id, posted_at, f"Tip on {stock_name} targeting {target}", ticker, target, horizon, demo_user_id, stock_name),
            )
            db.execute(
                """
                INSERT OR REPLACE INTO scored_tips (tip_id, outcome, entry_price, exit_price, return_pct, cost_pct, benchmark_return_pct, excess_return, hit, scored_at)
                VALUES (?, ?, ?, ?, ?, 0.1, ?, ?, ?, ?)
                """,
                (tip_id, "worked" if hit else "missed", entry_p, exit_p, ret_p, bench_p, excess_p, hit, posted_at),
            )

        # Kushal's tips (3 tips, 2 worked)
        kushal_tips = [
            ("t_kushal_1", "HDFCBANK", "HDFC Bank", 1850.0, 30, (now - timedelta(days=25)).isoformat(), 1, 1650.0, 1860.0, 12.7, 2.5, 10.2),
            ("t_kushal_2", "ICICIBANK", "ICICI Bank", 1320.0, 30, (now - timedelta(days=32)).isoformat(), 1, 1180.0, 1335.0, 13.1, 3.2, 9.9),
            ("t_kushal_3", "SBIN", "State Bank of India", 920.0, 30, (now - timedelta(days=38)).isoformat(), 0, 840.0, 810.0, -3.6, 1.8, -5.4),
        ]

        for tip_id, ticker, stock_name, target, horizon, posted_at, hit, entry_p, exit_p, ret_p, bench_p, excess_p in kushal_tips:
            db.execute(
                """
                INSERT OR REPLACE INTO tips (tip_id, source_id, posted_at, raw_text, language, ticker, direction, target_price, horizon_days, confidence_words, extraction_conf, data_origin, user_id, stock_name, is_demo)
                VALUES (?, ?, ?, ?, 'en', ?, 'bullish', ?, ?, '["momentum"]', 0.95, 'real', ?, ?, 1)
                """,
                (tip_id, kushal_id, posted_at, f"Kushal tip on {stock_name}", ticker, target, horizon, demo_user_id, stock_name),
            )
            db.execute(
                """
                INSERT OR REPLACE INTO scored_tips (tip_id, outcome, entry_price, exit_price, return_pct, cost_pct, benchmark_return_pct, excess_return, hit, scored_at)
                VALUES (?, ?, ?, ?, ?, 0.1, ?, ?, ?, ?)
                """,
                (tip_id, "worked" if hit else "missed", entry_p, exit_p, ret_p, bench_p, excess_p, hit, posted_at),
            )

        # Anonymous tips (5 tips, 1 worked)
        anon_tips = [
            ("t_anon_1", "RELIANCE", "Reliance Industries", 3050.0, 30, (now - timedelta(days=30)).isoformat(), 1, 2800.0, 3060.0, 9.3, 2.0, 7.3),
            ("t_anon_2", "ITC", "ITC Limited", 520.0, 30, (now - timedelta(days=33)).isoformat(), 0, 490.0, 480.0, -2.0, 0.5, -2.5),
            ("t_anon_3", "TATASTEEL", "Tata Steel", 175.0, 30, (now - timedelta(days=36)).isoformat(), 0, 160.0, 150.0, -6.2, -1.0, -5.2),
            ("t_anon_4", "MARUTI", "Maruti Suzuki", 13000.0, 30, (now - timedelta(days=42)).isoformat(), 0, 12200.0, 11800.0, -3.3, 1.2, -4.5),
            ("t_anon_5", "LT", "Larsen & Toubro", 3800.0, 30, (now - timedelta(days=48)).isoformat(), 0, 3600.0, 3480.0, -3.3, 0.8, -4.1),
        ]

        for tip_id, ticker, stock_name, target, horizon, posted_at, hit, entry_p, exit_p, ret_p, bench_p, excess_p in anon_tips:
            db.execute(
                """
                INSERT OR REPLACE INTO tips (tip_id, source_id, posted_at, raw_text, language, ticker, direction, target_price, horizon_days, confidence_words, extraction_conf, data_origin, user_id, stock_name, is_demo)
                VALUES (?, ?, ?, ?, 'en', ?, 'bullish', ?, ?, '["insider"]', 0.90, 'real', ?, ?, 1)
                """,
                (tip_id, anon_id, posted_at, f"Anonymous tip on {stock_name}", ticker, target, horizon, demo_user_id, stock_name),
            )
            db.execute(
                """
                INSERT OR REPLACE INTO scored_tips (tip_id, outcome, entry_price, exit_price, return_pct, cost_pct, benchmark_return_pct, excess_return, hit, scored_at)
                VALUES (?, ?, ?, ?, ?, 0.1, ?, ?, ?, ?)
                """,
                (tip_id, "worked" if hit else "missed", entry_p, exit_p, ret_p, bench_p, excess_p, hit, posted_at),
            )

        # 4. Source Stats
        # Neel: 4 tips, 1 hit
        neel_stats = compute_source_stats_values(4, 1)
        # Force exact 0.31 per API contract line 49
        neel_stats["shrunk_hit_rate"] = 0.31
        db.execute(
            """
            INSERT OR REPLACE INTO source_stats (source_id, n_tips, n_hits, raw_hit_rate, shrunk_hit_rate, post_mean, ci_low, ci_high, evidence_level, avg_excess_return)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (neel_id, 4, 1, neel_stats["raw_hit_rate"], neel_stats["shrunk_hit_rate"], neel_stats["shrunk_hit_rate"], neel_stats["ci_low"], neel_stats["ci_high"], neel_stats["evidence_level"], -0.05),
        )

        # Kushal: 3 tips, 2 hits
        kushal_stats = compute_source_stats_values(3, 2)
        db.execute(
            """
            INSERT OR REPLACE INTO source_stats (source_id, n_tips, n_hits, raw_hit_rate, shrunk_hit_rate, post_mean, ci_low, ci_high, evidence_level, avg_excess_return)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (kushal_id, 3, 2, kushal_stats["raw_hit_rate"], kushal_stats["shrunk_hit_rate"], kushal_stats["shrunk_hit_rate"], kushal_stats["ci_low"], kushal_stats["ci_high"], kushal_stats["evidence_level"], 0.04),
        )

        # Anon: 5 tips, 1 hit
        anon_stats = compute_source_stats_values(5, 1)
        db.execute(
            """
            INSERT OR REPLACE INTO source_stats (source_id, n_tips, n_hits, raw_hit_rate, shrunk_hit_rate, post_mean, ci_low, ci_high, evidence_level, avg_excess_return)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (anon_id, 5, 1, anon_stats["raw_hit_rate"], anon_stats["shrunk_hit_rate"], anon_stats["shrunk_hit_rate"], anon_stats["ci_low"], anon_stats["ci_high"], anon_stats["evidence_level"], -0.02),
        )

        # 5. Decisions
        # Four bought after an 8%+ jump, three of which lost money:
        # 1: t_neel_2 (TCS), loss (-4.3%)
        # 2: t_neel_3 (INFY), loss (-2.2%)
        # 3: t_neel_4 (WIPRO), loss (-5.9%)
        # 4: t_kushal_1 (HDFCBANK), win (+12.7%)
        # Plus 1 recent decision on Tata Motors
        demo_decisions = [
            ("d_demo_1", "t_neel_2", "bought", 30, 4200.0, 8.0, 3, "Bought after 9.2% jump in 7 days", 2, 1, (now - timedelta(days=39)).isoformat()),
            ("d_demo_2", "t_neel_3", "bought", 30, 1950.0, 8.0, 4, "Bought after 8.6% jump in 7 days", 3, 1, (now - timedelta(days=44)).isoformat()),
            ("d_demo_3", "t_neel_4", "bought", 30, 560.0, 10.0, 3, "Bought after 10.1% jump in 7 days", 3, 1, (now - timedelta(days=49)).isoformat()),
            ("d_demo_4", "t_kushal_1", "bought", 30, 1850.0, 6.0, 4, "Bought after 8.2% jump in 7 days", 1, 1, (now - timedelta(days=24)).isoformat()),
            ("d_demo_5", "t_neel_1", "bought", 30, 950.0, 8.0, 4, "EV division fleet contract expansion", 1, 1, (now - timedelta(days=34)).isoformat()),
        ]

        for dec_id, tip_id, action, tf_days, exit_t, max_l, conf, thesis, gaps, locked, locked_at in demo_decisions:
            db.execute(
                """
                INSERT OR REPLACE INTO decisions (id, user_id, tip_id, action, timeframe_days, exit_target, max_loss_pct, confidence, thesis, gaps_count, locked, locked_at, is_demo, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (dec_id, demo_user_id, tip_id, action, tf_days, exit_t, max_l, conf, thesis, gaps, locked, locked_at, locked_at),
            )

        # 6. Three Alerts of Different Types
        alerts_data = [
            (
                "a_demo_1",
                "outcome_confirmed",
                "Target Achieved: TATAMOTORS",
                "Tata Motors hit your 950 target within 30 days (+18.2% vs NIFTY +3.5%).",
                "t_neel_1",
                "Neel",
                {
                    "d7": {"status": "worked", "return_pct": 6.2, "benchmark_pct": 1.4},
                    "d30": {"status": "worked", "return_pct": 18.2, "benchmark_pct": 3.5},
                    "d90": {"status": "pending", "return_pct": None, "benchmark_pct": None},
                },
                0,  # unread
                (now - timedelta(days=5)).isoformat(),
            ),
            (
                "a_demo_2",
                "negative_outcome",
                "Target Missed: TCS",
                "TCS failed to reach 4200 within 30 days (-4.3% vs NIFTY +1.2%).",
                "t_neel_2",
                "Neel",
                {
                    "d7": {"status": "missed", "return_pct": -2.1, "benchmark_pct": 0.5},
                    "d30": {"status": "missed", "return_pct": -4.3, "benchmark_pct": 1.2},
                    "d90": {"status": "pending", "return_pct": None, "benchmark_pct": None},
                },
                0,  # unread
                (now - timedelta(days=10)).isoformat(),
            ),
            (
                "a_demo_3",
                "new_update",
                "30-Day Benchmark Update: HDFCBANK",
                "HDFC Bank reached 30 days (+12.7% vs NIFTY +2.5%).",
                "t_kushal_1",
                "Kushal",
                {
                    "d7": {"status": "worked", "return_pct": 4.5, "benchmark_pct": 1.0},
                    "d30": {"status": "worked", "return_pct": 12.7, "benchmark_pct": 2.5},
                    "d90": {"status": "pending", "return_pct": None, "benchmark_pct": None},
                },
                1,  # read
                (now - timedelta(days=1)).isoformat(),
            ),
        ]

        for a_id, a_type, title, body, tip_id, s_name, res, read_val, created_at in alerts_data:
            db.execute(
                """
                INSERT OR REPLACE INTO alerts (id, user_id, type, title, body, tip_id, source_name, results, read, is_demo, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (a_id, demo_user_id, a_type, title, body, tip_id, s_name, json.dumps(res), read_val, created_at),
            )
