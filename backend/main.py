"""
main.py – FastAPI application entry point.
Registers CORS middleware and mounts all API routers.
"""
import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from routers import generate_thread, train_voice   # Phase 2 endpoints
from routers import transcript, generate           # Phase 1 endpoints (kept for compatibility)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="VoiceThread API",
    description=(
        "Transform YouTube videos into Twitter threads that match your unique voice. "
        "Endpoints: POST /api/train-voice  |  POST /api/generate-thread"
    ),
    version="2.0.0",
)

# ---------------------------------------------------------------------------
# CORS – allow the React dev server (and production build) to call the API
# ---------------------------------------------------------------------------
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

_ALLOWED_ORIGINS = [
    frontend_origin,
    # Vite default and common fallback ports
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
    "http://localhost:8081",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:8081",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(_ALLOWED_ORIGINS)),  # deduplicate, preserve order
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(train_voice.router,     prefix="/api")   # POST /api/train-voice
app.include_router(generate_thread.router, prefix="/api")   # POST /api/generate-thread
app.include_router(transcript.router,      prefix="/api")   # POST /api/transcript
app.include_router(generate.router,        prefix="/api")   # POST /api/generate


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
