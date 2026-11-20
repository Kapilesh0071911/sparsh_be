from typing import Dict, List, Tuple

# Universal core questions (5)
UNIVERSAL_CORE_QUESTIONS: Dict[str, str] = {
    "core_timeframe": "What is your expected investment timeframe for this thesis to play out?",
    "core_falsification": "What specific event or metric would prove your thesis wrong and trigger an exit?",
    "core_revenue_impact": "What share of the company's total revenue or profit is actually affected by this catalyst?",
    "core_price_move": "Has the stock price already moved to price in this news or rumor?",
    "core_risk_capacity": "How much downside can you afford to lose if this thesis completely fails?",
}

# Sector-specific question templates (3 per sector)
SECTOR_QUESTIONS: Dict[str, Dict[str, str]] = {
    "auto": {
        "auto_ev_transition": "How vulnerable is their vehicle margin to commodity input costs (steel/batteries)?",
        "auto_channel_inventory": "Are dealer inventory levels rising or discounting widening in key segments?",
        "auto_capex_cycle": "Does their current EV or platform capex plan risk depressing near-term return on capital?",
    },
    "banking": {
        "banking_npa_asset_quality": "Are slippages or credit costs trending up in any specific lending book (e.g. unsecured retail)?",
        "banking_nim_compression": "Is deposit competition or cost of funds squeezing net interest margins (NIM)?",
        "banking_loan_growth": "Can loan growth outpace deposit growth without stretching liquidity coverage ratios?",
    },
    "it": {
        "it_discretionary_spend": "Is client discretionary IT spend improving or are contract decision cycles lengthening?",
        "it_attrition_margin": "Are wage revisions and sub-contracting costs impacting EBIT margins this quarter?",
        "it_geo_concentration": "What is their revenue exposure to US/European banking and retail headwinds?",
    },
    "pharma": {
        "pharma_usfda_compliance": "Are there any pending US FDA Form 483 inspection observations or import alerts on key facilities?",
        "pharma_price_erosion": "What is the expected generic price erosion rate in the US market for their top ANDA pipeline?",
        "pharma_domestic_formulation": "How resilient is their domestic chronic therapy segment against price controls (NLEM)?",
    },
    "fmcg": {
        "fmcg_rural_demand": "Is rural volume growth showing genuine recovery or is growth driven solely by price hikes?",
        "fmcg_raw_material": "Are palm oil, milk, and packaging costs inflating or softening for their product basket?",
        "fmcg_local_competition": "Are regional unorganized competitors regaining market share as commodity prices normalize?",
    },
    "energy": {
        "energy_refining_margin": "How are Gross Refining Margins (GRMs) or power purchase tariffs trending relative to historical averages?",
        "energy_regulation": "Is there risk of windfall tax, subsidized pricing, or government intervention on retail fuel margins?",
        "energy_transition": "How heavily is the company borrowing to finance its green energy transition?",
    },
    "metals": {
        "metals_china_demand": "Is Chinese industrial demand and steel export dumping exerting downward pressure on domestic realization?",
        "metals_coking_coal": "How exposed are margins to imported coking coal or iron ore spot price spikes?",
        "metals_debt_cycle": "Does the current debt-to-EBITDA ratio leave enough buffer for the down-cycle in spot commodity prices?",
    },
    "other": {
        "other_competitive_moat": "Does the company have clear pricing power or a moat against competitors copying this move?",
        "other_valuation": "Is the current valuation (P/E or EV/EBITDA) reasonable compared to its 5-year historical median?",
        "other_corporate_governance": "Are there promoter pledging, auditor turnover, or related-party transaction concerns?",
    },
}

TICKER_SECTOR_MAP: Dict[str, str] = {
    # Auto
    "TATAMOTORS": "auto",
    "MARUTI": "auto",
    "M&M": "auto",
    "BAJAJ-AUTO": "auto",
    "HEROMOTOCO": "auto",
    "EICHERMOT": "auto",
    "TVSMOTOR": "auto",
    # Banking & Financials
    "HDFCBANK": "banking",
    "ICICIBANK": "banking",
    "SBIN": "banking",
    "KOTAKBANK": "banking",
    "AXISBANK": "banking",
    "BAJFINANCE": "banking",
    "INDUSINDBK": "banking",
    # IT
    "TCS": "it",
    "INFY": "it",
    "WIPRO": "it",
    "HCLTECH": "it",
    "TECHM": "it",
    "LTIM": "it",
    # Pharma & Healthcare
    "SUNPHARMA": "pharma",
    "CIPLA": "pharma",
    "DRREDDY": "pharma",
    "DIVISLAB": "pharma",
    "LUPIN": "pharma",
    "APOLLOHOSP": "pharma",
    # FMCG & Food
    "ITC": "fmcg",
    "HINDUNILVR": "fmcg",
    "NESTLEIND": "fmcg",
    "BRITANNIA": "fmcg",
    "TATACONSUM": "fmcg",
    "DABUR": "fmcg",
    "MARICO": "fmcg",
    # Energy & Utilities
    "RELIANCE": "energy",
    "ONGC": "energy",
    "NTPC": "energy",
    "POWERGRID": "energy",
    "BPCL": "energy",
    "COALINDIA": "energy",
    # Metals & Mining
    "TATASTEEL": "metals",
    "JSWSTEEL": "metals",
    "HINDALCO": "metals",
    "VEDL": "metals",
}


def get_sector_for_ticker(ticker: str) -> str:
    cleaned = ticker.upper().replace(".NS", "").replace(".BO", "").strip()
    return TICKER_SECTOR_MAP.get(cleaned, "other")


def get_question_text(key: str) -> str:
    if key in UNIVERSAL_CORE_QUESTIONS:
        return UNIVERSAL_CORE_QUESTIONS[key]
    for sector, qmap in SECTOR_QUESTIONS.items():
        if key in qmap:
            return qmap[key]
    return "What other critical risks or assumptions are you considering?"


def get_all_questions_for_ticker(ticker: str) -> List[Tuple[str, str]]:
    """Returns ordered list of (key, question_text) for ticker."""
    questions = []
    # Interleave core questions and sector-specific questions
    sector = get_sector_for_ticker(ticker)
    sector_dict = SECTOR_QUESTIONS.get(sector, SECTOR_QUESTIONS["other"])

    core_items = list(UNIVERSAL_CORE_QUESTIONS.items())
    sector_items = list(sector_dict.items())

    # Build sequence:
    # 1. core timeframe
    # 2. sector Q 1
    # 3. core falsification
    # 4. sector Q 2
    # 5. core revenue impact
    # 6. sector Q 3
    # 7. core price move
    # 8. core risk capacity
    interleaved: List[Tuple[str, str]] = []
    if len(core_items) > 0:
        interleaved.append(core_items[0])
    if len(sector_items) > 0:
        interleaved.append(sector_items[0])
    if len(core_items) > 1:
        interleaved.append(core_items[1])
    if len(sector_items) > 1:
        interleaved.append(sector_items[1])
    if len(core_items) > 2:
        interleaved.append(core_items[2])
    if len(sector_items) > 2:
        interleaved.append(sector_items[2])
    if len(core_items) > 3:
        interleaved.append(core_items[3])
    if len(core_items) > 4:
        interleaved.append(core_items[4])

    return interleaved
