"""
transcript.py – endpoint to fetch a YouTube video transcript.

POST /api/transcript
Body: { "url": "https://www.youtube.com/watch?v=..." }
Returns: { "transcript": "full plain-text transcript", "video_id": "..." }

Updated for youtube-transcript-api v1.2+ which uses the new fetch() API.
"""
import urllib.parse
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    IpBlocked,
    RequestBlocked,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["transcript"])


class TranscriptRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def must_be_youtube(cls, v: str) -> str:
        if not any(domain in v for domain in ["youtube.com", "youtu.be"]):
            raise ValueError("Not a recognisable YouTube URL.")
        return v.strip()


class TranscriptResponse(BaseModel):
    video_id: str
    transcript: str
    status: str = "success"


def _extract_video_id(url: str) -> str:
    """
    Safely extracts the 11-character video ID from any YouTube URL.
    """
    try:
        parsed_url = urllib.parse.urlparse(url)
        
        # Handle youtu.be short URLs
        if "youtu.be" in parsed_url.netloc:
            video_id = parsed_url.path.lstrip("/").split("?")[0]
            return video_id if len(video_id) == 11 else None
        
        # Handle youtube.com URLs
        if "youtube.com" in parsed_url.netloc:
            # Standard watch URLs: ?v=VIDEO_ID
            if "watch" in parsed_url.path or "v=" in parsed_url.query:
                query = urllib.parse.parse_qs(parsed_url.query)
                video_id = query.get("v", [None])[0]
                return video_id if video_id and len(video_id) == 11 else None
            
            # Shorts and embed URLs
            path_parts = parsed_url.path.strip("/").split("/")
            if len(path_parts) >= 2 and path_parts[0] in ["shorts", "embed"]:
                video_id = path_parts[1].split("?")[0]
                return video_id if len(video_id) == 11 else None
    
    except Exception as e:
        logger.error(f"Error parsing YouTube URL: {e}")
        return None
    
    return None


@router.post("/transcript", response_model=TranscriptResponse)
def fetch_transcript(body: TranscriptRequest) -> TranscriptResponse:
    """
    Extract the spoken transcript from a YouTube video URL.
    
    Uses the modern fetch() API from youtube-transcript-api v1.2+
    """
    video_id = _extract_video_id(body.url)
    
    if not video_id:
        logger.warning(f"Invalid YouTube URL format: {body.url}")
        raise HTTPException(
            status_code=400,
            detail="Invalid YouTube URL format. Please provide a valid youtube.com or youtu.be link."
        )

    yt_api = YouTubeTranscriptApi()

    try:
        # Try English variants first; fall back to any available language
        try:
            logger.info(f"Fetching transcript for video: {video_id}")
            transcript_list = yt_api.fetch(video_id, languages=['en', 'en-US', 'en-GB'])
        except NoTranscriptFound:
            logger.info(f"No English transcript for {video_id}, retrying without language filter")
            transcript_list = yt_api.fetch(video_id)

        full_text = " ".join([item.text for item in transcript_list])
        logger.info(f"✓ Successfully fetched transcript for {video_id} ({len(full_text)} chars)")

        return TranscriptResponse(
            video_id=video_id,
            transcript=full_text,
            status="success"
        )

    except TranscriptsDisabled:
        logger.warning(f"Transcripts disabled for video: {video_id}")
        raise HTTPException(
            status_code=400,
            detail="The creator of this video has disabled closed captions. Please try a different video."
        )
    except NoTranscriptFound:
        logger.warning(f"No transcript found for video: {video_id}")
        raise HTTPException(
            status_code=400,
            detail="No subtitles (manual or auto-generated) were found for this video."
        )
    except VideoUnavailable:
        logger.warning(f"Video unavailable: {video_id}")
        raise HTTPException(
            status_code=404,
            detail="Video not found or unavailable. Please check the URL."
        )
    except (IpBlocked, RequestBlocked) as e:
        logger.error(f"YouTube blocked the request for {video_id}: {e}")
        raise HTTPException(
            status_code=503,
            detail="YouTube is blocking transcript requests from this server. Please try again later."
        )
    except Exception as e:
        logger.error(f"Unexpected error fetching transcript for {video_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch transcript: {str(e)}"
        )
