from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import APP_NAME, CORS_ORIGINS
from app.core.database import init_db
from app.core.exceptions import AppException
from app.services.seed import seed_demo_data
from app.services.scoring import start_scheduler, shutdown_scheduler

# Routers
from app.api.routes import router as api_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.decisions import router as decisions_router
from app.api.investments import router as investments_router
from app.api.insights import router as insights_router
from app.api.alerts import router as alerts_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_demo_data()
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title=APP_NAME,
    version="1.0.0",
    description="Tip Checkpoint API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = {}
    missing_fields = []
    for err in exc.errors():
        loc = err.get("loc", ())
        field_name = str(loc[-1]) if loc else "field"
        details[field_name] = err.get("msg")
        if err.get("type") in ("missing", "value_error.missing"):
            missing_fields.append(field_name)

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Validation error",
                "details": {"missing_fields": missing_fields} if missing_fields else details,
            }
        },
    )





@app.get("/")
def root():
    return {
        "success": True,
        "message": "Tip Checkpoint API is running",
        "docs": "/docs",
    }


@app.get("/api/v1/meta")
def get_meta():
    return {
        "success": True,
        "app": APP_NAME,
        "version": "1.0.0",
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Include original API routes (existing endpoints under /api/v1)
app.include_router(api_router)

# Include new API v1 routers per API contract
app.include_router(auth_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(decisions_router, prefix="/api/v1")
app.include_router(investments_router, prefix="/api/v1")
app.include_router(insights_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")

# Also mount under root to support clients connecting directly
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(decisions_router)
app.include_router(investments_router)
app.include_router(insights_router)
app.include_router(alerts_router)
