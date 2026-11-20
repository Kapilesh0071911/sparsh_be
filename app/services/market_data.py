from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from app.core.config import LLM_MODE

# Fallback prices and 7d changes for common Indian tickers
MOCK_MARKET_DATA = {
    "TATAMOTORS": {"price_now": 812.4, "change_7d_pct": 6.2},
    "TCS": {"price_now": 3950.0, "change_7d_pct": 1.5},
    "INFY": {"price_now": 1820.0, "change_7d_pct": 2.1},
    "HDFCBANK": {"price_now": 1740.0, "change_7d_pct": 3.4},
    "ICICIBANK": {"price_now": 1245.0, "change_7d_pct": 4.1},
    "SBIN": {"price_now": 820.0, "change_7d_pct": -1.2},
    "RELIANCE": {"price_now": 2890.0, "change_7d_pct": 1.8},
    "ITC": {"price_now": 485.0, "change_7d_pct": 0.5},
    "WIPRO": {"price_now": 510.0, "change_7d_pct": -2.0},
    "TATASTEEL": {"price_now": 152.0, "change_7d_pct": 8.5},
}


def clean_ticker(ticker: str) -> str:
    return ticker.upper().replace(".NS", "").replace(".BO", "").strip()


def get_context_data(ticker: str) -> Dict[str, Any]:
    cleaned = clean_ticker(ticker)
    price_now = None
    change_7d_pct = None

    # In mock mode, immediately return deterministic data without network latency
    if LLM_MODE != "mock":
        try:
            import yfinance as yf
            yf_symbol = f"{cleaned}.NS"
            t = yf.Ticker(yf_symbol)
            hist = t.history(period="1mo")
            if hist is not None and not hist.empty and len(hist) >= 6:
                price_now = round(float(hist["Close"].iloc[-1]), 2)
                idx = max(0, len(hist) - 6)
                prev_price = float(hist["Close"].iloc[idx])
                if prev_price > 0:
                    change_7d_pct = round(((price_now - prev_price) / prev_price) * 100, 2)
        except Exception:
            pass

    if price_now is None or change_7d_pct is None:
        mock = MOCK_MARKET_DATA.get(cleaned, {"price_now": 500.0, "change_7d_pct": 3.5})
        price_now = mock["price_now"]
        change_7d_pct = mock["change_7d_pct"]

    note = (
        f"Already up {change_7d_pct}% in the last 7 days."
        if change_7d_pct >= 0
        else f"Down {abs(change_7d_pct)}% in the last 7 days."
    )

    return {
        "ticker": cleaned,
        "price_now": price_now,
        "change_7d_pct": change_7d_pct,
        "since_tip_pct": None,
        "note": note,
    }


def get_price_at_dates(ticker: str, posted_at: datetime) -> Dict[str, Any]:
    """
    Computes prices at posted_at, +7d, +30d, +90d, and benchmark NIFTY 50 returns.
    Falls back gracefully if live market data is not reachable.
    """
    cleaned = clean_ticker(ticker)
    now = datetime.now(timezone.utc)
    elapsed_days = (now - posted_at).days

    if LLM_MODE != "mock":
        try:
            import yfinance as yf
            yf_ticker = yf.Ticker(f"{cleaned}.NS")
            hist = yf_ticker.history(start=posted_at.strftime("%Y-%m-%d"), end=(now + timedelta(days=1)).strftime("%Y-%m-%d"))
            yf_bench = yf.Ticker("^NSEI")
            bench_hist = yf_bench.history(start=posted_at.strftime("%Y-%m-%d"), end=(now + timedelta(days=1)).strftime("%Y-%m-%d"))

            if not hist.empty and len(hist) > 0:
                entry_price = float(hist["Close"].iloc[0])
                bench_entry = float(bench_hist["Close"].iloc[0]) if not bench_hist.empty else 24000.0

                def get_window_res(days_target):
                    if elapsed_days < days_target:
                        return {"status": "pending", "return_pct": None, "benchmark_pct": None, "exit_price": None}
                    target_date = posted_at + timedelta(days=days_target)
                    subset = hist.loc[:target_date.strftime("%Y-%m-%d")]
                    if subset.empty:
                        subset = hist
                    exit_price = float(subset["Close"].iloc[-1])
                    ret_pct = round(((exit_price - entry_price) / entry_price) * 100, 2)

                    b_subset = bench_hist.loc[:target_date.strftime("%Y-%m-%d")] if not bench_hist.empty else None
                    b_exit = float(b_subset["Close"].iloc[-1]) if (b_subset is not None and not b_subset.empty) else bench_entry
                    b_ret_pct = round(((b_exit - bench_entry) / bench_entry) * 100, 2)

                    return {
                        "return_pct": ret_pct,
                        "benchmark_pct": b_ret_pct,
                        "exit_price": exit_price,
                        "max_price": float(subset["High"].max()),
                    }

                return {
                    "entry_price": entry_price,
                    "d7": get_window_res(7),
                    "d30": get_window_res(30),
                    "d90": get_window_res(90),
                }
        except Exception:
            pass

    # Deterministic fallback simulation
    base_price = MOCK_MARKET_DATA.get(cleaned, {}).get("price_now", 500.0)
    return {
        "entry_price": base_price,
        "d7": {
            "return_pct": 4.1 if elapsed_days >= 7 else None,
            "benchmark_pct": 1.2 if elapsed_days >= 7 else None,
            "exit_price": round(base_price * 1.041, 2) if elapsed_days >= 7 else None,
            "status": "worked" if elapsed_days >= 7 else "pending",
        },
        "d30": {
            "return_pct": 8.5 if elapsed_days >= 30 else None,
            "benchmark_pct": 2.0 if elapsed_days >= 30 else None,
            "exit_price": round(base_price * 1.085, 2) if elapsed_days >= 30 else None,
            "status": "worked" if elapsed_days >= 30 else "pending",
        },
        "d90": {
            "return_pct": None,
            "benchmark_pct": None,
            "exit_price": None,
            "status": "pending",
        },
    }
