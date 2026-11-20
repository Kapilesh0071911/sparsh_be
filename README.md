# Tip Checkpoint (SIGNAL / NOISE) — Backend

FastAPI + SQLite backend for Tip Checkpoint, extending the fixed API contract with conversational intake, thesis auditing, decision gate validation, investment tracking, behavioral insights, and source credibility scoring.

## Features
- **Authentication**: JWT-based auth (`/auth/signup`, `/auth/login`, `/auth/me`) with bcrypt-hashed passwords.
- **Chat State Machine**:
  - `intake`: Stock tip extraction (vision LLM / mock demo), source resolution, claim card, source record, 7-day market context card.
  - `awaiting_thesis`: User provides reasoning; causal chain decomposition (3–7 links) with evidence checking.
  - `questioning`: Fixed universal & sector-specific question templates; strict one-question-per-turn rule and 6-question maximum cap.
  - `gate`: Complete decision gate with required validation before locking.
  - `locked`: Locked decisions only updated via backend validation; LLM cannot lock decisions.
- **Investment Tracking**: Completed purchase detection, tokenized confirmation (`POST /investments/confirm`), and position tracking (`GET /investments`).
- **Decision Insights**: SQL analytics identifying behavioural trading patterns (e.g. buying after 8%+ jumps and loss rates).
- **Credibility Scoring & Alerts**: Daily APScheduler job & manual scoring function evaluating 7, 30, and 90-day returns against NIFTY 50 (`^NSEI`), recomputing shrunk hit rates, and generating milestone alerts.
- **Demo Seed Data**: Pre-seeded demo account with personal sources (Neel, Kushal), anonymous tips, past scored outcomes, and sample alerts.

---

## Getting Started

### 1. Prerequisites
- Python 3.11+
- Virtual environment (`.venv`)

### 2. Setup & Installation
```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
python -m pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```powershell
cp .env.example .env
```
Default configuration:
```env
APP_NAME=Tip Checkpoint API
DB_PATH=app/data/tip_checkpoint.db
FRONTEND_ORIGIN=http://localhost:5173

# Auth
JWT_SECRET=supersecret-key-tip-checkpoint-jwt-2026
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# LLM: mock (offline demo) or live (gemini, openai)
LLM_PROVIDER=gemini
LLM_API_KEY=
LLM_MODE=mock
```

### 4. Run the Backend Server
```powershell
uvicorn app.main:app --reload --port 8000
```
- API Base URL: `http://localhost:8000/api/v1`
- Swagger UI Documentation: `http://localhost:8000/docs`

### 5. Demo Credentials
- **Email**: `demo@signalnoise.app`
- **Password**: `demo1234`

### 6. Run Tests
```powershell
pytest -v
```

---

## API Summary (Base URL: `/api/v1`)

### Auth
- `POST /auth/signup`
- `POST /auth/login`
- `GET /auth/me`

### Chat
- `POST /chat/message` (`multipart/form-data`)
- `GET /conversations/{conversation_id}`

### Decisions
- `POST /decisions/lock`
- `GET /decisions`

### Investments
- `POST /investments/confirm`
- `GET /investments`

### Insights
- `GET /insights`

### Alerts
- `GET /alerts`
- `POST /alerts/{id}/read`
- `POST /alerts/read_all`

### Sources
- `GET /sources` (extended with credibility metrics: `shrunk_hit_rate`, `evidence_level`, `label`)

### Pre-Existing Endpoints (Kept Unchanged)
- `GET /`
- `GET /api/v1/meta`
- `GET /api/health`
- `GET /sources/{id}`
- `GET /tips/{id}`
- `GET /coordination/flags`
- `GET /coordination/graph`
- `GET /archive/*`
- `POST /analyze`
- `POST /eval/*`
