"""
generate_thread.py  –  POST /api/generate-thread

Phase 2 unified endpoint.

Flow:
  1. Parse & validate the YouTube URL.
  2. Fetch the video transcript via youtube-transcript-api.
  3. Query Mem0 (Hindsight) for consolidated style observations for this creator.
  4. Build a voice-matched prompt (system = Hindsight observations, user = transcript).
  5. Call Google Gemini inside a Cascadeflow agent (latency + cost guardrails).
  6. Return the structured thread with Cascadeflow telemetry.

Request body:
    {
        "creator_id": "user_123",
        "youtube_url": "https://www.youtube.com/watch?v=EXAMPLE",
        "tweet_count": 5          # optional, 3-10
    }

Success response (200):
    {
        "status": "success",
        "cascadeflow_metrics": {"cost": 0.00, "latency_ms": 1200},
        "thread": ["tweet 1", "tweet 2", ...]
    }
"""
from __future__ import annotations

import json
import os
import re
import time
import logging
from typing import Any

from google import genai
from google.genai import types as genai_types
import groq as groq_sdk
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from mem0 import MemoryClient
from youtube_transcript_api import YouTubeTranscriptApi
import cascadeflow
from cascadeflow.harness import agent as cf_agent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generate-thread"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# ~15 minutes of spoken content at 2.5 words/second
_MAX_TRANSCRIPT_WORDS = 2_250

# Regex that matches standard, short, embed, and Shorts YouTube URLs
_YT_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})"
)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class GenerateThreadRequest(BaseModel):
    creator_id: str = Field(
        ..., min_length=1, description="The creator's unique identifier."
    )
    youtube_url: str = Field(default="", description="Full YouTube video URL (optional if transcript provided).")
    transcript: str = Field(default="", description="Direct transcript text (optional if youtube_url provided).")
    tweet_count: int = Field(
        default=5, ge=3, le=10, description="Number of tweets in the thread."
    )
    platform: str = Field(
        default="twitter", description="Target platform: 'twitter' or 'linkedin'"
    )

    @field_validator("youtube_url")
    @classmethod
    def must_be_youtube_if_provided(cls, v: str) -> str:
        if v and not _YT_ID_RE.search(v):
            raise ValueError(
                "Invalid YouTube URL. Must contain a recognisable video ID "
                "(e.g. ?v=..., youtu.be/..., /shorts/...)."
            )
        return v.strip() if v else ""
    
    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str) -> str:
        platform = v.strip().lower()
        if platform not in ["twitter", "linkedin"]:
            raise ValueError("Platform must be either 'twitter' or 'linkedin'")
        return platform
    
    def model_post_init(self, __context):
        """Ensure at least one of youtube_url or transcript is provided."""
        if not self.youtube_url and not self.transcript:
            raise ValueError("Either youtube_url or transcript must be provided")


# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------

_mem0_client: MemoryClient | None = None
_cascadeflow_initialised = False


def _get_mem0() -> MemoryClient:
    global _mem0_client
    if _mem0_client is not None:
        return _mem0_client

    api_key = os.getenv("MEM0_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "MEM0_API_KEY is not configured. Add it to your .env file."
        )
    _mem0_client = MemoryClient(api_key=api_key)
    return _mem0_client


def _ensure_cascadeflow() -> None:
    """Initialise Cascadeflow once per process in observe mode."""
    global _cascadeflow_initialised
    if _cascadeflow_initialised:
        return

    cf_key = os.getenv("CASCADEFLOW_API_KEY")
    # Mode options: "observe" (track only) | "enforce" (block on limits)
    cf_mode = os.getenv("CASCADEFLOW_MODE", "enforce")
    
    if cf_key:
        cascadeflow.init(api_key=cf_key, mode=cf_mode)
    else:
        # Graceful degradation — run without remote telemetry
        logger.info(
            "CASCADEFLOW_API_KEY not set; running Cascadeflow in local %s mode.",
            cf_mode
        )
        cascadeflow.init(mode=cf_mode)

    _cascadeflow_initialised = True


def _get_gemini_client() -> tuple[genai.Client, str]:
    """Return a configured Gemini client and the model name to use."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not configured. Add it to your .env file."
        )
    client = genai.Client(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    return client, model_name


def _get_groq_client() -> tuple[groq_sdk.Groq, str]:
    """Return a configured Groq client and the model name to use."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY is not configured. Add it to your .env file."
        )
    client = groq_sdk.Groq(api_key=api_key)
    model_name = os.getenv("GROQ_MODEL", "llama3-8b-8192")
    return client, model_name


# ---------------------------------------------------------------------------
# Step 1 – Transcript extraction
# ---------------------------------------------------------------------------

def _extract_video_id(url: str) -> str:
    match = _YT_ID_RE.search(url)
    if not match:
        raise ValueError("Could not parse video ID from URL.")
    return match.group(1)


def _fetch_transcript(video_id: str) -> str:
    """
    Download and concatenate the full video transcript using the modern
    fetch() API (youtube-transcript-api v1.2+).
    
    Raises ValueError with a user-friendly message on any failure.
    Truncates to _MAX_TRANSCRIPT_WORDS (≈ 15 minutes of speech).
    """
    try:
        # NEW API (v1.2+): Instantiate then call fetch()
        logger.info(f"Fetching transcript for video: {video_id}")
        yt_api = YouTubeTranscriptApi()
        segments = yt_api.fetch(video_id, languages=['en', 'en-US', 'en-GB'])
        
    except Exception as e:
        # Fallback: Try without language specification
        logger.warning(f"Explicit English fetch failed, trying fallback: {e}")
        try:
            fallback_api = YouTubeTranscriptApi()
            segments = fallback_api.fetch(video_id)
        except Exception as inner_exc:
            error_msg = str(inner_exc)
            logger.error(f"Both transcript methods failed for {video_id}: {error_msg}")
            
            if "disabled" in error_msg.lower():
                raise ValueError(
                    "Transcripts are disabled for this video. "
                    "The creator has turned off captions — try a different video."
                )
            elif "unavailable" in error_msg.lower() or "not found" in error_msg.lower():
                raise ValueError(
                    "Video not found or unavailable. Check the URL and try again."
                )
            elif "no english" in error_msg.lower() or "captions" in error_msg.lower():
                raise ValueError(
                    "No English transcript available for this video. "
                    "Ensure the video has closed captions enabled."
                )
            else:
                raise ValueError(f"Unexpected error fetching transcript: {inner_exc}") from inner_exc

    # Concatenate all text segments
    full_text = " ".join(seg["text"] for seg in segments)

    # Truncate if too long
    words = full_text.split()
    if len(words) > _MAX_TRANSCRIPT_WORDS:
        logger.info(
            "Transcript truncated from %d to %d words (15-min cap).",
            len(words),
            _MAX_TRANSCRIPT_WORDS,
        )
        full_text = " ".join(words[:_MAX_TRANSCRIPT_WORDS])

    logger.info(f"✓ Successfully fetched transcript ({len(full_text)} chars)")
    return full_text


# ---------------------------------------------------------------------------
# Step 2 – Hindsight memory retrieval
# ---------------------------------------------------------------------------

def _recall_voice_style(creator_id: str, topic_hint: str, platform: str = "twitter") -> str:
    """
    Query Mem0 for style observations consolidated from the creator's past
    voice samples.  Returns a plain-text block ready to inject into the prompt.

    Falls back gracefully when the memory bank is empty or on API errors.
    """
    try:
        client = _get_mem0()
        # Include platform context in the search query
        search_query = f"Platform: {platform}. Topic: {topic_hint}"
        results = client.search(
            query=search_query,
            filters={"user_id": creator_id},
            top_k=10,
        )

        # results is a dict with a "results" list of memory objects
        memories: list[dict[str, Any]] = (
            results.get("results", []) if isinstance(results, dict) else results
        )

        if not memories:
            logger.info(
                "No Hindsight observations found for creator '%s' on %s. "
                "Using cold-start fallback.",
                creator_id,
                platform,
            )
            return ""

        lines = []
        for m in memories:
            text = m.get("memory", "")
            if text:
                lines.append(f"- {text}")

        return "\n".join(lines)

    except EnvironmentError:
        # MEM0_API_KEY not set — skip memory silently
        logger.warning("Mem0 not configured; proceeding without voice memory.")
        return ""
    except Exception as exc:
        logger.warning(
            "Hindsight recall failed for creator '%s': %s. Continuing without memory.",
            creator_id,
            exc,
        )
        return ""


# ---------------------------------------------------------------------------
# Step 3 – Prompt engineering
# ---------------------------------------------------------------------------

_BASE_INSTRUCTIONS = """\
You are an expert social media ghostwriter.

Your task: summarise the VIDEO TRANSCRIPT below into a {tweet_count}-part {platform} post.

CRITICAL RULES — follow every one:
1. You MUST write in the creator's EXACT tone, style, slang, vocabulary, sentence length,
   punctuation habits, and emoji usage as described in the CREATOR DIRECTIVES below.
2. Do NOT use generic AI phrases: "In this video…", "Key takeaways:", "Let's dive in",
   "In conclusion", or any filler opener.
3. {platform_specific_rules}
4. The first part must hook the reader with the most surprising or provocative insight.
5. The last part must end with a punchy call-to-action or memorable closer.

OUTPUT FORMAT INSTRUCTIONS:
- DO NOT use JSON. DO NOT use arrays. DO NOT use brackets or quotes.
- Write exactly {tweet_count} parts as plain text.
- Separate each part using exactly three pipe characters: |||
- Example format: First part here ||| Second part here ||| Third part here\
"""

_TWITTER_RULES = "Every tweet MUST be ≤ 280 characters. Keep it punchy and engaging."

_LINKEDIN_RULES = """\
Format for LinkedIn carousel/post style:
- Use professional but engaging language
- Add strategic line breaks for readability
- Each part can be longer than Twitter (aim for 200-400 chars per part)
- Use emojis sparingly and professionally
- Focus on value delivery and storytelling\
"""

_COLD_START_NOTICE = """\
NOTE: No prior style data exists for this creator yet. Write in a natural,
conversational Twitter voice — informal, direct, punchy.\
"""


def _build_prompt(
    transcript: str,
    style_observations: str,
    tweet_count: int,
    platform: str = "twitter",
) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) for the Gemini chat call.
    Adapts formatting based on the target platform (twitter or linkedin).
    """
    # Select platform-specific rules
    platform_rules = _TWITTER_RULES if platform == "twitter" else _LINKEDIN_RULES
    platform_name = "Twitter" if platform == "twitter" else "LinkedIn"
    
    system_lines = [
        _BASE_INSTRUCTIONS.format(
            tweet_count=tweet_count,
            platform=platform_name,
            platform_specific_rules=platform_rules
        )
    ]

    if style_observations:
        system_lines.append(
            "\n---\nCREATOR DIRECTIVES (Hindsight observations — obey these above all else):\n"
            + style_observations
        )
    else:
        system_lines.append("\n---\n" + _COLD_START_NOTICE)

    system_prompt = "\n".join(system_lines)

    user_prompt = (
        f"VIDEO TRANSCRIPT:\n{transcript.strip()}\n\n"
        f"---\nWrite the {tweet_count}-part {platform_name} post now:"
    )

    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Step 4 – Cascadeflow-wrapped Gemini call
# ---------------------------------------------------------------------------

def _parse_thread(raw: str, expected: int) -> list[str]:
    """
    Parse the model's raw output into individual tweet strings using the delimiter method.

    Primary path: Split by ||| delimiter (gracefully handles truncation).
    Fallback: Double-newline split if delimiter not found.
    
    This approach is far more resilient than JSON parsing when dealing with
    network interruptions or token limit truncation.
    
    AMPUTATION BUG FIX: If the AI generates more than the expected number of parts,
    we merge all overflow parts into the final slot instead of chopping them off.
    This prevents mid-sentence truncation in the UI.
    """
    # Primary: Delimiter-based split (bulletproof)
    if "|||" in raw:
        tweets = [t.strip() for t in raw.split("|||") if t.strip()]
        
        # GRACEFUL MERGING: If we have more parts than expected, combine the overflow
        if len(tweets) > expected:
            logger.info(
                "AI generated %d parts but expected %d — merging overflow into final part",
                len(tweets),
                expected
            )
            # Combine everything from index (expected-1) onwards into one string
            tweets[expected - 1] = " ".join(tweets[expected - 1:])
            # Now safe to slice without losing content
            tweets = tweets[:expected]
        
        return tweets
    
    # Fallback: Double-newline split
    tweets = [t.strip() for t in raw.strip().split("\n\n") if t.strip()]
    
    # Apply same graceful merging logic to fallback path
    if len(tweets) > expected:
        logger.info(
            "Fallback split: AI generated %d parts but expected %d — merging overflow",
            len(tweets),
            expected
        )
        tweets[expected - 1] = " ".join(tweets[expected - 1:])
        tweets = tweets[:expected]
    
    if not tweets:
        # Last resort: return the raw output as a single tweet
        return [raw.strip()[:280]] if raw.strip() else ["Failed to generate thread."]
    
    return tweets


def _call_gemini_with_cascadeflow(
    system_prompt: str,
    user_prompt: str,
    gemini_client: genai.Client,
    model_name: str,
    tweet_count: int,
) -> tuple[list[str], dict[str, Any]]:
    """
    Wraps the Gemini API call inside a Cascadeflow agent to capture
    latency and cost metrics, and enforce runtime budget limits.

    Returns (thread_tweets, cascadeflow_metrics).
    """
    latency_limit_ms = int(os.getenv("CASCADEFLOW_LATENCY_LIMIT_MS", "30000"))
    cost_limit_usd = float(os.getenv("CASCADEFLOW_COST_LIMIT_USD", "0.05"))

    metrics: dict[str, Any] = {"cost": 0.0, "latency_ms": 0}

    @cf_agent(
        budget=cost_limit_usd,
        compliance="none",
    )
    def _agent_fn() -> str:
        response = gemini_client.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                max_output_tokens=2048,  # Generous limit to prevent truncation
                # Disable safety filters that block educational/medical content
                safety_settings=[
                    genai_types.SafetySetting(
                        category="HARM_CATEGORY_DANGEROUS_CONTENT",
                        threshold="BLOCK_NONE"
                    ),
                    genai_types.SafetySetting(
                        category="HARM_CATEGORY_HARASSMENT",
                        threshold="BLOCK_NONE"
                    ),
                    genai_types.SafetySetting(
                        category="HARM_CATEGORY_HATE_SPEECH",
                        threshold="BLOCK_NONE"
                    ),
                    genai_types.SafetySetting(
                        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        threshold="BLOCK_NONE"
                    ),
                ],
            ),
        )
        return response.text

    t0 = time.monotonic()
    result = _agent_fn()
    elapsed_ms = round((time.monotonic() - t0) * 1000)

    # Cascadeflow may return a CascadeResult wrapper or the raw string
    if hasattr(result, "output"):
        raw_text = result.output
        metrics["cost"] = getattr(result, "cost", 0.0) or 0.0
        metrics["latency_ms"] = getattr(result, "latency_ms", None) or elapsed_ms
    else:
        raw_text = result
        metrics["latency_ms"] = elapsed_ms

    thread = _parse_thread(raw_text, tweet_count)
    return thread, metrics


def _call_groq_fallback(
    system_prompt: str,
    user_prompt: str,
    groq_client: groq_sdk.Groq,
    model_name: str,
    tweet_count: int,
) -> tuple[list[str], dict[str, Any]]:
    """
    Fallback thread generation using Groq (Llama 3).

    Uses the same delimiter-based approach for consistency and resilience.

    Returns (thread_tweets, cascadeflow_metrics).
    """
    t0 = time.monotonic()

    completion = groq_client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=2048,
    )

    elapsed_ms = round((time.monotonic() - t0) * 1000)
    raw_text = completion.choices[0].message.content or ""

    thread = _parse_thread(raw_text, tweet_count)
    metrics: dict[str, Any] = {"cost": 0.0, "latency_ms": elapsed_ms, "provider": "groq"}
    return thread, metrics


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/generate-thread")
def generate_thread(body: GenerateThreadRequest) -> JSONResponse:
    """
    Memory-driven, observability-wrapped thread generation.

    1. Extract YouTube transcript.
    2. Recall Hindsight style observations for this creator.
    3. Build prompt (system = observations, user = transcript).
    4. Call Gemini inside Cascadeflow agent (latency + cost guardrails).
    5. Return thread + Cascadeflow telemetry.
    """

    # ── 1. Parse video ID (if URL provided) ──────────────────────────────────
    video_id = None
    if body.youtube_url:
        try:
            video_id = _extract_video_id(body.youtube_url)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": str(exc)},
            )

    # ── 2. Fetch or use provided transcript ──────────────────────────────────
    if body.transcript:
        # Use the provided transcript directly
        transcript = body.transcript
        logger.info("Using provided transcript (%d chars)", len(transcript))
    elif video_id:
        # Fetch from YouTube
        try:
            transcript = _fetch_transcript(video_id)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": str(exc)},
            )
    else:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Either youtube_url or transcript must be provided."},
        )

    # ── 3. Recall Hindsight style memory ────────────────────────────────────
    # Use first ~100 chars of transcript as the topic hint for semantic search
    topic_hint = transcript[:100]
    style_observations = _recall_voice_style(body.creator_id, topic_hint, body.platform)

    # ── 4. Initialise runtime tools ──────────────────────────────────────────
    try:
        gemini_client, model_name = _get_gemini_client()
    except EnvironmentError as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": str(exc)},
        )

    _ensure_cascadeflow()

    # ── 5. Build prompt ──────────────────────────────────────────────────────
    system_prompt, user_prompt = _build_prompt(
        transcript, style_observations, body.tweet_count, body.platform
    )

    # ── 6. Cascadeflow-wrapped Gemini call (with Groq fallback) ──────────────
    try:
        thread, cf_metrics = _call_gemini_with_cascadeflow(
            system_prompt, user_prompt, gemini_client, model_name, body.tweet_count
        )
        cf_metrics.setdefault("provider", "gemini")
    except cascadeflow.BudgetExceededError as exc:
        logger.warning("Cascadeflow budget exceeded: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": (
                    "Request aborted: cost or latency limit exceeded. "
                    "Try a shorter video or increase the budget limits."
                ),
            },
        )
    except Exception as gemini_exc:
        logger.warning(
            "Gemini generation failed (%s) — retrying with Groq fallback.", gemini_exc
        )
        try:
            groq_client, groq_model = _get_groq_client()
            thread, cf_metrics = _call_groq_fallback(
                system_prompt, user_prompt, groq_client, groq_model, body.tweet_count
            )
            logger.info("Groq fallback succeeded | tweets=%d", len(thread))
        except Exception as groq_exc:
            logger.exception("Groq fallback also failed.")
            return JSONResponse(
                status_code=502,
                content={
                    "status": "error",
                    "message": (
                        f"Both AI providers failed. "
                        f"Gemini: {gemini_exc}. Groq: {groq_exc}."
                    ),
                },
            )

    # ── 7. Return structured response ────────────────────────────────────────
    logger.info(
        "Thread generated for creator '%s' | tweets=%d | latency=%dms | cost=$%.5f",
        body.creator_id,
        len(thread),
        cf_metrics.get("latency_ms", 0),
        cf_metrics.get("cost", 0.0),
    )

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "cascadeflow_metrics": cf_metrics,
            "thread": thread,
        },
    )
