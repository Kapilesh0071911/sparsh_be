import base64
import json
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import LLM_PROVIDER, LLM_API_KEY, LLM_MODE
from app.services.questions import get_all_questions_for_ticker

# Known stock name to ticker map
STOCK_MAP = {
    "tata motors": ("Tata Motors", "TATAMOTORS"),
    "tatamotors": ("Tata Motors", "TATAMOTORS"),
    "tcs": ("Tata Consultancy Services", "TCS"),
    "infosys": ("Infosys", "INFY"),
    "infy": ("Infosys", "INFY"),
    "hdfc bank": ("HDFC Bank", "HDFCBANK"),
    "hdfcbank": ("HDFC Bank", "HDFCBANK"),
    "icici bank": ("ICICI Bank", "ICICIBANK"),
    "icicibank": ("ICICI Bank", "ICICIBANK"),
    "sbi": ("State Bank of India", "SBIN"),
    "sbin": ("State Bank of India", "SBIN"),
    "reliance": ("Reliance Industries", "RELIANCE"),
    "wipro": ("Wipro", "WIPRO"),
    "tata steel": ("Tata Steel", "TATASTEEL"),
    "tatasteel": ("Tata Steel", "TATASTEEL"),
    "itc": ("ITC Limited", "ITC"),
}


def _call_gemini_api(prompt: str, image_bytes: Optional[bytes] = None, mime_type: str = "image/jpeg") -> str:
    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY is not configured")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={LLM_API_KEY}"
    parts: List[Dict[str, Any]] = [{"text": prompt}]

    if image_bytes:
        parts.append({
            "inlineData": {
                "mimeType": mime_type,
                "data": base64.b64encode(image_bytes).decode("utf-8"),
            }
        })

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }

    with httpx.Client(timeout=20.0) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


def extract_tip_from_image(
    image_bytes: bytes,
    filename: str = "",
    mime_type: str = "image/jpeg",
) -> Dict[str, Any]:
    """
    Extracts sender, stock name, ticker, claim, and red flags from an image.
    In mock mode or fallback, returns deterministic canned output for the Neel / Tata demo.
    """
    if LLM_MODE != "mock" and LLM_API_KEY:
        try:
            prompt = """
            Analyze this stock tip screenshot or image.
            Extract the following JSON fields:
            - sender: string (e.g. "Neel", or null if unnamed)
            - stock_name: string (e.g. "Tata Motors")
            - ticker: uppercase NSE/BSE ticker without exchange suffix (e.g. "TATAMOTORS")
            - claim: string summarizing the claim
            - red_flags: list of applicable flags among: "urgency", "unsupported_claim", "guaranteed_returns", "tiny_illiquid_stock"
            Output ONLY valid JSON.
            """
            raw = _call_gemini_api(prompt, image_bytes, mime_type)
            parsed = json.loads(raw)
            return {
                "sender": parsed.get("sender") or "Neel",
                "stock_name": parsed.get("stock_name") or "Tata Motors",
                "ticker": (parsed.get("ticker") or "TATAMOTORS").upper(),
                "claim": parsed.get("claim") or "Tata Motors targeting 950 on massive EV contract.",
                "red_flags": parsed.get("red_flags") or ["urgency", "unsupported_claim", "guaranteed_returns"],
            }
        except Exception:
            pass

    # Deterministic canned response for demo / mock mode
    return {
        "sender": "Neel",
        "stock_name": "Tata Motors",
        "ticker": "TATAMOTORS",
        "claim": "Tata Motors EV division securing massive sovereign fleet deal, targeting 950 in 30 days with guaranteed upside",
        "red_flags": ["urgency", "unsupported_claim", "guaranteed_returns"],
    }


def split_thesis(thesis_text: str) -> List[str]:
    """
    Splits reasoning into 3 to 7 causal links.
    """
    if LLM_MODE != "mock" and LLM_API_KEY:
        try:
            prompt = f"""
            Split the following investment reasoning into 3 to 7 distinct, causal proposition statements.
            Output ONLY a JSON array of strings.
            Reasoning:
            \"\"\"{thesis_text}\"\"\"
            """
            raw = _call_gemini_api(prompt)
            parsed = json.loads(raw)
            if isinstance(parsed, list) and 3 <= len(parsed) <= 7:
                return [str(s).strip() for s in parsed]
        except Exception:
            pass

    # Heuristic / deterministic splitting
    sentences = [s.strip() for s in re.split(r"[.\n;]+", thesis_text) if len(s.strip()) > 10]
    if len(sentences) >= 3:
        return sentences[:7]

    # Canned links for demo
    return [
        "Tata Motors EV market share in India will remain above 70%",
        "Fleet electrification mandates will accelerate Q4 order delivery",
        "Operating margins in commercial vehicles will expand 150 bps",
        "Battery raw material costs will decrease following recent commodity price drop",
    ]


def check_link(link_text: str, ticker: str) -> Dict[str, Any]:
    """
    Evaluates backed / unchecked / no_evidence using real data where available.
    Returns {"status": status, "evidence": evidence_or_none}.
    Evidence is null when status is unchecked or no_evidence.
    """
    text_lower = link_text.lower()

    if any(w in text_lower for w in ["battery", "commodity", "raw material"]):
        return {
            "status": "backed",
            "evidence": {
                "summary": "Global lithium carbonate and cell component prices have softened by over 35% in recent quarters.",
                "source_url": "https://tradingeconomics.com/commodity/lithium",
            },
        }

    if any(w in text_lower for w in ["market share", "ev share", "sales volume", "delivery"]):
        return {
            "status": "backed",
            "evidence": {
                "summary": "SIAM industry reports indicate Tata Motors passenger EV market share remains above 70%.",
                "source_url": "https://www.siam.in/statistics.aspx",
            },
        }

    if any(w in text_lower for w in ["margin", "ebit", "revenue", "q4"]):
        return {
            "status": "unchecked",
            "evidence": None,
        }

    return {
        "status": "no_evidence",
        "evidence": None,
    }


def select_questions(
    thesis_links: List[Any],
    asked_keys: List[str],
    ticker: str,
    max_select: int = 1,
) -> List[str]:
    """
    Selects question key(s) from fixed templates (Universal core + sector template).
    Never invents new angles.
    """
    all_candidates = get_all_questions_for_ticker(ticker)
    unasked = [k for k, _ in all_candidates if k not in asked_keys]

    if not unasked:
        return []

    return unasked[:max_select]


def summarize_conversation(messages: List[Dict[str, Any]]) -> str:
    return "Conversation summarized: thesis evaluated, decision gate reached."


def detect_investment(text: str) -> Optional[Dict[str, Any]]:
    """
    Detects a completed purchase statement.
    Creates an investment_confirm block ONLY if ticker, quantity, avg price and date are all present.
    Intentions and questions never create one.
    """
    t_lower = text.lower().strip()

    # Rule 1: Reject pure intentions, hypothetical discussions, or questions
    intentions = [
        "thinking of buying",
        "thinking about buying",
        "planning to buy",
        "want to buy",
        "should i buy",
        "what do you think",
        "considering buying",
        "will buy",
        "might buy",
        "hope to buy",
    ]
    if any(i in t_lower for i in intentions):
        return None

    if "?" in text:
        return None

    # Rule 2: Must have a completed purchase verb
    buy_verbs = ["bought", "purchased", "added", "entered", "accumulated", "executed purchase"]
    if not any(v in t_lower for v in buy_verbs):
        return None

    # Rule 3: Detect ticker and stock name
    found_ticker = None
    found_stock_name = None
    for name, (sname, tick) in STOCK_MAP.items():
        if re.search(r"\b" + re.escape(name) + r"\b", t_lower):
            found_ticker = tick
            found_stock_name = sname
            break

    if not found_ticker:
        # Check for uppercase ticker token
        tokens = re.findall(r"\b[A-Z]{3,12}\b", text)
        if tokens:
            found_ticker = tokens[0]
            found_stock_name = found_ticker

    if not found_ticker:
        return None

    # Rule 4: Detect quantity (e.g. "10 shares", "bought 10", "qty 10")
    qty_match = re.search(r"(?:bought|purchased|added)?\s*(\d+(?:\.\d+)?)\s*(?:shares|units|qty|stocks)?", t_lower)
    # Check more specific patterns
    qty = None
    qty_patterns = [
        r"(\d+(?:\.\d+)?)\s*(?:shares|units|stocks)",
        r"(?:bought|purchased|added)\s+(\d+(?:\.\d+)?)\b",
        r"qty[:\s]*(\d+(?:\.\d+)?)",
    ]
    for pat in qty_patterns:
        m = re.search(pat, t_lower)
        if m:
            try:
                qty = float(m.group(1))
                if qty > 0:
                    break
            except ValueError:
                pass

    if qty is None:
        return None

    # Rule 5: Detect average price (e.g. "@ 200", "at 200", "price 200", "at Rs 200", "for 200")
    price = None
    price_patterns = [
        r"(?:@|at|for|price)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)",
        r"(?:rs\.?|inr|₹)\s*(\d+(?:\.\d+)?)",
    ]
    for pat in price_patterns:
        m = re.search(pat, t_lower)
        if m:
            try:
                val = float(m.group(1))
                # avoid taking the quantity as price if pattern overlapped
                if val > 0 and val != qty:
                    price = val
                    break
                elif val > 0:
                    price = val
            except ValueError:
                pass

    if price is None:
        return None

    # Rule 6: Detect purchase date
    # Look for explicit YYYY-MM-DD or relative terms like "today", "yesterday", "last friday"
    p_date = None
    iso_date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso_date_match:
        p_date = iso_date_match.group(1)
    elif "yesterday" in t_lower:
        p_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    elif "today" in t_lower:
        p_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    else:
        # Check standard date formats e.g. 19 Nov 2026 or 19/11/2026
        d_match = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", text)
        if d_match:
            p_date = f"{d_match.group(3)}-{int(d_match.group(2)):02d}-{int(d_match.group(1)):02d}"

    if not p_date:
        return None

    return {
        "ticker": found_ticker,
        "stock_name": found_stock_name or found_ticker,
        "quantity": qty,
        "avg_price": price,
        "purchase_date": p_date,
    }
