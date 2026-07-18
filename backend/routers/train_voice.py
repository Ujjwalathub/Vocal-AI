"""
train_voice.py  –  POST /api/train-voice

Ingests the creator's past tweets / writing samples into the Mem0 (Hindsight)
memory bank so they can be recalled later during thread generation.

Request body:
    {
        "creator_id": "user_123",
        "voice_samples": [
            "Just spent 4 hours debugging CSS... send coffee ☕️😭 #webdev",
            "Hot take: React is great, but sometimes plain HTML/JS is all you need."
        ]
    }

Success response (200):
    {
        "status": "success",
        "message": "Stored 2 voice sample(s) for creator user_123.",
        "memories_added": 2
    }
"""
from __future__ import annotations

import os
import logging
from typing import Annotated

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from mem0 import MemoryClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["train-voice"])

# ---------------------------------------------------------------------------
# Mem0 client – lazy singleton
# ---------------------------------------------------------------------------

_mem0_client: MemoryClient | None = None


def _get_mem0() -> MemoryClient:
    global _mem0_client
    if _mem0_client is not None:
        return _mem0_client

    api_key = os.getenv("MEM0_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "MEM0_API_KEY is not configured. "
            "Add it to your .env file (see .env.example)."
        )

    _mem0_client = MemoryClient(api_key=api_key)
    return _mem0_client


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class TrainVoiceRequest(BaseModel):
    creator_id: str = Field(
        ...,
        min_length=1,
        description="Stable unique ID for the creator (e.g. 'user_123').",
    )
    voice_samples: Annotated[
        list[str],
        Field(..., min_length=1, description="List of past tweets or writing samples."),
    ]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/train-voice")
def train_voice(body: TrainVoiceRequest) -> JSONResponse:
    """
    Retain the creator's voice samples into the Mem0 (Hindsight) memory bank.
    Mem0 automatically consolidates these over time into higher-level
    'Observations' (e.g. 'Creator uses informal tech slang and emojis').
    """
    # Clean empty strings before storing
    samples = [s.strip() for s in body.voice_samples if s.strip()]
    if not samples:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "voice_samples must contain at least one non-empty string.",
            },
        )

    try:
        client = _get_mem0()
    except EnvironmentError as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": str(exc)},
        )

    # Each sample is sent as a user message so Mem0 can extract facts / style
    # observations about this creator automatically.
    messages = [{"role": "user", "content": s} for s in samples]

    try:
        client.add(
            messages,
            user_id=body.creator_id,
            output_format="v1.1",
        )
        logger.info(
            "Stored %d voice sample(s) for creator '%s'.",
            len(samples),
            body.creator_id,
        )
    except Exception as exc:
        logger.exception("Mem0 retain failed for creator '%s'.", body.creator_id)
        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "message": f"Memory storage failed: {exc}",
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": (
                f"Stored {len(samples)} voice sample(s) for creator {body.creator_id}."
            ),
            "memories_added": len(samples),
        },
    )
