"""
generate.py – legacy Phase 1 endpoint (kept for backwards compatibility).
Calls IBM watsonx.ai to produce a Twitter thread from a raw transcript.

POST /api/generate
Body: { "transcript": "...", "voice_samples": "...", "tweet_count": 5 }
Returns: { "thread": ["tweet 1", "tweet 2", ...] }

NOTE: This endpoint requires ibm-watsonx-ai to be installed.  If the package
is absent the router is still registered but all calls will return 503.
"""
import os
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from ibm_watsonx_ai import APIClient, Credentials
    from ibm_watsonx_ai.foundation_models import ModelInference
    from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams
    _WATSONX_AVAILABLE = True
except ImportError:
    _WATSONX_AVAILABLE = False

router = APIRouter(tags=["generate"])

# ---------------------------------------------------------------------------
# Watsonx client (lazy-initialised so the import doesn't fail without creds)
# ---------------------------------------------------------------------------
_client = None


def _get_model():
    global _client

    if not _WATSONX_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=(
                "ibm-watsonx-ai is not installed. "
                "This legacy endpoint is disabled. Use POST /api/generate-thread instead."
            ),
        )

    if _client is not None:
        return _client

    api_key = os.getenv("WATSONX_API_KEY")
    project_id = os.getenv("WATSONX_PROJECT_ID")
    url = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
    model_id = os.getenv("WATSONX_MODEL_ID", "ibm/granite-13b-chat-v2")

    if not api_key or not project_id:
        raise HTTPException(
            status_code=503,
            detail=(
                "IBM watsonx.ai credentials are not configured. "
                "Set WATSONX_API_KEY and WATSONX_PROJECT_ID in the .env file."
            ),
        )

    credentials = Credentials(url=url, api_key=api_key)
    _client = ModelInference(
        model_id=model_id,
        credentials=credentials,
        project_id=project_id,
        params={
            GenParams.MAX_NEW_TOKENS: 1024,
            GenParams.TEMPERATURE: 0.7,
            GenParams.TOP_P: 0.9,
            GenParams.REPETITION_PENALTY: 1.1,
        },
    )
    return _client


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """You are a social media ghostwriter. Your task is to write a Twitter thread based on the video transcript provided, but the writing style, vocabulary, tone, humor, and sentence structure must EXACTLY match the voice samples given.

Rules:
- Write exactly {tweet_count} tweets numbered as "1/", "2/", etc.
- Each tweet must be under 280 characters.
- Preserve the creator's unique quirks, slang, and phrasing from the voice samples.
- Do NOT sound like an AI. Do NOT use generic phrases like "In this video..." or "Key takeaways:".
- Capture the most interesting / shareable insight from the transcript for each tweet.
- The first tweet should hook the reader. The last tweet should be a call to action or punchy closer.
- Output ONLY the numbered tweets, nothing else."""


def _build_prompt(transcript: str, voice_samples: str, tweet_count: int) -> str:
    # Truncate transcript to avoid exceeding context window (~3000 words is safe)
    words = transcript.split()
    if len(words) > 3000:
        transcript = " ".join(words[:3000]) + " [transcript truncated]"

    system = _SYSTEM_PROMPT.format(tweet_count=tweet_count)

    return f"""{system}

---
VOICE SAMPLES (the creator's real past tweets — match this style exactly):
{voice_samples.strip()}

---
VIDEO TRANSCRIPT:
{transcript.strip()}

---
Write the {tweet_count}-tweet thread now:
"""


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------
def _parse_thread(raw: str, expected: int) -> list[str]:
    """Extract numbered tweets from the model's raw output."""
    # Match lines that start with a tweet number like "1/" or "1."
    pattern = re.compile(r"^\s*\d+[/\.]\s*", re.MULTILINE)
    parts = pattern.split(raw)
    # First element is empty (before "1/")
    tweets = [t.strip() for t in parts if t.strip()]

    if not tweets:
        # Fallback: split by double newlines
        tweets = [t.strip() for t in raw.strip().split("\n\n") if t.strip()]

    # If still nothing useful, return the raw text as a single item
    if not tweets:
        return [raw.strip()]

    return tweets[:expected]


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class GenerateRequest(BaseModel):
    transcript: str = Field(..., min_length=50)
    voice_samples: str = Field(..., min_length=20)
    tweet_count: int = Field(default=5, ge=3, le=10)


class GenerateResponse(BaseModel):
    thread: list[str]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@router.post("/generate", response_model=GenerateResponse)
def generate_thread(body: GenerateRequest) -> GenerateResponse:
    """Generate a Twitter thread from a transcript in the creator's voice."""
    model = _get_model()
    prompt = _build_prompt(body.transcript, body.voice_samples, body.tweet_count)

    try:
        response = model.generate_text(prompt=prompt)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"watsonx.ai generation failed: {exc}",
        ) from exc

    thread = _parse_thread(response, body.tweet_count)
    return GenerateResponse(thread=thread)
