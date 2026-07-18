import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";

// Backend API base URL
const API_BASE = "http://localhost:8000/api";

export const trainVoice = createServerFn({ method: "POST" })
  .inputValidator((data) =>
    z.object({
      samples: z.string().min(20, "Provide at least 20 characters of writing samples"),
      creatorId: z.string(),
    }).parse(data),
  )
  .handler(async ({ data }) => {
    // Split samples by double newlines to create an array
    const samplesArray = data.samples
      .split(/\n\n+/)
      .map(s => s.trim())
      .filter(Boolean);

    const response = await fetch(`${API_BASE}/train-voice`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        creator_id: data.creatorId,
        voice_samples: samplesArray,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: "Failed to train voice" }));
      throw new Error(error.message || error.detail || "Voice training failed");
    }

    await response.json();
    
    // Analyze the samples for display
    const words = data.samples.split(/\s+/).filter(Boolean);
    const avgLen = words.length ? words.reduce((a, w) => a + w.length, 0) / words.length : 0;
    
    return {
      ok: true,
      voiceId: data.creatorId,
      stats: {
        wordCount: words.length,
        avgWordLength: Number(avgLen.toFixed(2)),
        tone: avgLen > 5.5 ? "considered & precise" : "punchy & conversational",
      },
    };
  });

export const fetchTranscript = createServerFn({ method: "POST" })
  .inputValidator((data) =>
    z.object({ url: z.string().url("Enter a valid YouTube URL") }).parse(data),
  )
  .handler(async ({ data }) => {
    const idMatch = data.url.match(/(?:v=|youtu\.be\/|shorts\/)([\w-]{6,})/);
    const videoId = idMatch?.[1];
    
    if (!videoId) {
      throw new Error("Invalid YouTube URL");
    }

    const response = await fetch(`${API_BASE}/transcript`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: data.url }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Failed to fetch transcript" }));
      throw new Error(error.detail || error.message || "Transcript fetch failed");
    }

    const result = await response.json();
    
    return {
      ok: true,
      videoId: result.video_id || videoId,
      transcript: result.transcript || "No transcript available",
    };
  });

export const generateThread = createServerFn({ method: "POST" })
  .inputValidator((data) =>
    z
      .object({
        transcript: z.string().min(10, "Transcript is required"),
        voiceId: z.string().optional(),
        creatorId: z.string().optional(),
        platform: z.enum(["twitter", "linkedin"]).default("twitter"),
      })
      .parse(data),
  )
  .handler(async ({ data }) => {
    const response = await fetch(`${API_BASE}/generate-thread`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        creator_id: data.creatorId ?? data.voiceId ?? "anonymous",
        transcript: data.transcript,
        tweet_count: data.platform === "linkedin" ? 7 : 5,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Failed to generate thread" }));
      throw new Error(error.detail || error.message || "Thread generation failed");
    }

    const result = await response.json();
    
    return {
      ok: true,
      platform: data.platform,
      posts: result.thread || ["Error: No thread generated"],
    };
  });
