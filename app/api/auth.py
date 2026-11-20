import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status

from app.core.database import connect
from app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)
from app.core.exceptions import validation_error, unauthorized_error
from app.schemas.contract_models import (
    SignupRequest,
    LoginRequest,
    AuthResponse,
    UserResponse,
    User,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=AuthResponse)
def signup(req: SignupRequest):
    email = req.email.strip().lower()
    name = req.name.strip()
    password = req.password

    with connect() as db:
        existing = db.execute(
            "SELECT id FROM users WHERE LOWER(email) = ?",
            (email,),
        ).fetchone()

        if existing:
            raise validation_error("Email already registered", {"email": "Already exists"})

        user_id = f"u_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        pwd_hash = hash_password(password)

        db.execute(
            """
            INSERT INTO users (id, name, email, password_hash, is_demo, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (user_id, name, email, pwd_hash, now),
        )

    token = create_access_token(user_id, email)
    return AuthResponse(
        token=token,
        user=User(id=user_id, name=name, email=email),
    )


@router.post("/login", status_code=status.HTTP_200_OK, response_model=AuthResponse)
def login(req: LoginRequest):
    email = req.email.strip().lower()
    password = req.password

    with connect() as db:
        user = db.execute(
            "SELECT id, name, email, password_hash FROM users WHERE LOWER(email) = ?",
            (email,),
        ).fetchone()

    if not user or not verify_password(password, user["password_hash"]):
        raise unauthorized_error("Invalid email or password")

    token = create_access_token(user["id"], user["email"])
    return AuthResponse(
        token=token,
        user=User(id=user["id"], name=user["name"], email=user["email"]),
    )


@router.get("/me", status_code=status.HTTP_200_OK, response_model=UserResponse)
def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        user=User(
            id=current_user["id"],
            name=current_user["name"],
            email=current_user["email"],
        )
    )
