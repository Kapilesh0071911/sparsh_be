import os
from dotenv import load_dotenv

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "Tip Checkpoint API")
DB_PATH = os.getenv("DB_PATH", "app/data/tip_checkpoint.db")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

# JWT Auth
JWT_SECRET = os.getenv("JWT_SECRET", "supersecret-key-tip-checkpoint-jwt-2026")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

# LLM Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODE = os.getenv("LLM_MODE", "mock").lower()

# CORS Allowed Origins
CORS_ORIGINS = [
    FRONTEND_ORIGIN,
    "http://localhost:5173",
    "http://localhost:3000",
]
