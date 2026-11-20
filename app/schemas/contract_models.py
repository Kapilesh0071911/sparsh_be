from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


# ---------------------------------------------------------
# AUTH MODELS
# ---------------------------------------------------------

class User(BaseModel):
    id: str
    name: str
    email: str


class SignupRequest(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    password: str = Field(min_length=4)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class AuthResponse(BaseModel):
    token: str
    user: User


class UserResponse(BaseModel):
    user: User


# ---------------------------------------------------------
# CHAT BLOCKS & RESPONSES
# ---------------------------------------------------------

StageType = Literal[
    "intake",
    "awaiting_thesis",
    "auditing",
    "questioning",
    "gate",
    "locked",
    "chitchat",
]


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    content: str


class StockRef(BaseModel):
    name: str
    ticker: str


class ClaimCardBlock(BaseModel):
    type: Literal["claim_card"] = "claim_card"
    tip_id: str
    sender: str
    source_id: str
    stock: StockRef
    claim: str
    red_flags: List[str] = Field(default_factory=list)


class SourceRecordBlock(BaseModel):
    type: Literal["source_record"] = "source_record"
    source_id: str
    source_name: str
    tips_total: int
    tips_worked: int
    shrunk_hit_rate: float
    evidence_level: Literal["none", "low", "medium", "high"]
    label: str


class ContextCardBlock(BaseModel):
    type: Literal["context_card"] = "context_card"
    ticker: str
    price_now: float
    change_7d_pct: float
    since_tip_pct: Optional[float] = None
    note: str


class EvidenceItem(BaseModel):
    summary: str
    source_url: Optional[str] = None


class ThesisLink(BaseModel):
    id: str
    text: str
    status: Literal["backed", "unchecked", "no_evidence"]
    evidence: Optional[EvidenceItem] = None


class ThesisChainBlock(BaseModel):
    type: Literal["thesis_chain"] = "thesis_chain"
    links: List[ThesisLink]
    gaps_count: int
    total_links: int
    summary: str


class DecisionGateValues(BaseModel):
    action: Optional[Literal["bought", "skipped", "watching"]] = None
    timeframe_days: Optional[int] = None
    exit_target: Optional[float] = None
    max_loss_pct: Optional[float] = None
    confidence: Optional[int] = None


class DecisionGateBlock(BaseModel):
    type: Literal["decision_gate"] = "decision_gate"
    decision_id: str
    tip_id: str
    required_fields: List[str] = [
        "action",
        "timeframe_days",
        "exit_target",
        "max_loss_pct",
        "confidence",
    ]
    values: DecisionGateValues = DecisionGateValues()
    locked: bool = False
    locked_at: Optional[str] = None


class InsightBlock(BaseModel):
    type: Literal["insight"] = "insight"
    text: str


class InvestmentDraft(BaseModel):
    ticker: str
    stock_name: str
    quantity: float
    avg_price: float
    purchase_date: str


class InvestmentConfirmBlock(BaseModel):
    type: Literal["investment_confirm"] = "investment_confirm"
    confirm_token: str
    draft: InvestmentDraft


ChatBlock = Union[
    TextBlock,
    ClaimCardBlock,
    SourceRecordBlock,
    ContextCardBlock,
    ThesisChainBlock,
    DecisionGateBlock,
    InsightBlock,
    InvestmentConfirmBlock,
]


class QuickReply(BaseModel):
    label: str
    value: str


class ChatMessageResponse(BaseModel):
    conversation_id: str
    stage: StageType
    questions_asked: int
    questions_max: int = 6
    blocks: List[Dict[str, Any]]
    quick_replies: List[QuickReply] = Field(default_factory=list)


class MessageItem(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    created_at: str
    image_url: Optional[str] = None
    blocks: List[Dict[str, Any]]


class ConversationDetailResponse(BaseModel):
    conversation_id: str
    stage: StageType
    questions_asked: int
    questions_max: int = 6
    messages: List[MessageItem]


# ---------------------------------------------------------
# DECISIONS
# ---------------------------------------------------------

class DecisionLockRequest(BaseModel):
    decision_id: Optional[str] = None
    action: Optional[str] = None
    timeframe_days: Optional[Any] = None
    exit_target: Optional[Any] = None
    max_loss_pct: Optional[Any] = None
    confidence: Optional[Any] = None


class Decision(BaseModel):
    id: str
    tip_id: str
    action: str
    timeframe_days: int
    exit_target: float
    max_loss_pct: float
    confidence: int
    thesis: Optional[str] = None
    gaps_count: int
    locked_at: Optional[str] = None


class DecisionWithStock(Decision):
    stock: StockRef
    source_name: str


class DecisionLockResponse(BaseModel):
    decision: Decision


class DecisionsListResponse(BaseModel):
    decisions: List[DecisionWithStock]


# ---------------------------------------------------------
# INVESTMENTS
# ---------------------------------------------------------

class InvestmentConfirmRequest(BaseModel):
    confirm_token: str
    ticker: Optional[str] = None
    quantity: Optional[float] = None
    avg_price: Optional[float] = None
    purchase_date: Optional[str] = None


class Investment(BaseModel):
    id: str
    ticker: str
    stock_name: str
    quantity: float
    avg_price: float
    purchase_date: str
    current_price: Optional[float] = None
    current_value: Optional[float] = None
    linked_tip_id: Optional[str] = None


class InvestmentConfirmResponse(BaseModel):
    investment: Investment


class InvestmentsListResponse(BaseModel):
    investments: List[Investment]


# ---------------------------------------------------------
# INSIGHTS
# ---------------------------------------------------------

class InsightItem(BaseModel):
    id: str
    text: str
    evidence_count: int


class InsightsListResponse(BaseModel):
    insights: List[InsightItem]


# ---------------------------------------------------------
# ALERTS
# ---------------------------------------------------------

class AlertResult(BaseModel):
    status: Literal["worked", "missed", "pending"]
    return_pct: Optional[float] = None
    benchmark_pct: Optional[float] = None


class AlertResults(BaseModel):
    d7: AlertResult
    d30: AlertResult
    d90: AlertResult


class AlertOut(BaseModel):
    id: str
    type: Literal["outcome_confirmed", "negative_outcome", "new_update"]
    title: str
    body: str
    tip_id: str
    source_name: str
    results: AlertResults
    created_at: str
    read: bool


class AlertsListResponse(BaseModel):
    unread_count: int
    alerts: List[AlertOut]


class AlertReadResponse(BaseModel):
    unread_count: int


# ---------------------------------------------------------
# SOURCES
# ---------------------------------------------------------

class SourceItem(BaseModel):
    id: str
    name: str
    type: Literal["friend", "anonymous", "finfluencer"]
    tips_total: int
    tips_worked: int
    raw_hit_rate: Optional[float] = None
    shrunk_hit_rate: Optional[float] = None
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    evidence_level: Literal["none", "low", "medium", "high"]
    label: str


class SourcesResponse(BaseModel):
    sources: List[SourceItem]
