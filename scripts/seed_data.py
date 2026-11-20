

import random
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import connect

random.seed(42)

sources = [
    ("SRC001", "Market Pulse India", "social_media"),
    ("SRC002", "Equity Insights", "telegram"),
    ("SRC003", "Stock Radar", "social_media"),
    ("SRC004", "Bull Signals", "telegram"),
    ("SRC005", "Trade Journal India", "social_media"),
    ("SRC006", "Alpha Tracker", "telegram"),
    ("SRC007", "Investor Lens", "social_media"),
    ("SRC008", "Market Whisper", "telegram"),
    ("SRC009", "Trend Capital", "social_media"),
    ("SRC010", "Value Finder", "telegram"),
]

tickers = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
            "WIPRO", "ITC", "SBIN", "LT", "TATAMOTORS"]

directions = ["bullish", "bearish"]

confidence_words = [
    ["strong breakout", "high confidence"],
    ["possible upside", "watch closely"],
    ["accumulation", "positive momentum"],
    ["weak outlook", "downside risk"],
    ["long-term potential"],
    ["momentum trade"],
]

now = datetime.now(timezone.utc)

with connect() as db:

    for source_id, name, source_type in sources:
        db.execute("""
            INSERT OR IGNORE INTO sources
            (source_id, display_name, source_type, sebi_registered, data_origin)
            VALUES (?, ?, ?, ?, ?)
        """, (source_id, name, source_type, 0, "synthetic"))

    for i in range(1, 51):
        tip_id = f"TIP{i:03d}"
        source = random.choice(sources)
        ticker = random.choice(tickers)
        direction = random.choice(directions)

        posted_at = now - timedelta(days=random.randint(1, 90))

        target_price = round(random.uniform(100, 3000), 2)
        horizon_days = random.choice([7, 15, 30, 45, 60, 90])

        words = random.choice(confidence_words)

        raw_text = (
            f"SYNTHETIC SAMPLE: {ticker} looks "
            f"{'positive' if direction == 'bullish' else 'negative'} "
            f"over the next {horizon_days} days. "
            f"Target price mentioned: {target_price}. "
            f"Confidence terms: {', '.join(words)}."
        )

        db.execute("""
            INSERT OR IGNORE INTO tips (
                tip_id, source_id, posted_at, raw_text, language,
                ticker, direction, target_price, horizon_days,
                confidence_words, extraction_conf, data_origin
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tip_id,
            source[0],
            posted_at.isoformat(),
            raw_text,
            "en",
            ticker,
            direction,
            target_price,
            horizon_days,
            json.dumps(words),
            round(random.uniform(0.75, 0.99), 2),
            "synthetic"
        ))

print("Synthetic dataset inserted successfully.")
print("Sources: 10")
print("Tips: 50")
