import { createFileRoute } from "@tanstack/react-router";
import { useServerFn } from "@tanstack/react-start";
import { useState } from "react";
import {
  Mic,
  Youtube,
  Sparkles,
  Wand2,
  Waves,
  ScrollText,
  ArrowRight,
  Check,
  AlertCircle,
  Loader2,
  Copy,
} from "lucide-react";
import heroImg from "@/assets/hero-illustration.png";
import {
  trainVoice,
  fetchTranscript,
  generateThread,
} from "@/lib/voicethread.functions";

// Resolved once in the browser; never on the server (server functions receive it as input).
function getCreatorId(): string {
  const stored = localStorage.getItem("creatorId");
  if (stored) return stored;
  const id = `creator_${Date.now().toString(36)}`;
  localStorage.setItem("creatorId", id);
  return id;
}

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "VoiceThread — Turn YouTube videos into threads in your voice" },
      {
        name: "description",
        content:
          "VoiceThread learns how you write, pulls transcripts from any YouTube video, and generates social threads that sound authentically like you.",
      },
      { property: "og:title", content: "VoiceThread — YouTube → threads, in your voice" },
      {
        property: "og:description",
        content:
          "Train a voice model on your writing, drop a YouTube URL, and get a polished thread in seconds.",
      },
      { property: "og:type", content: "website" },
    ],
  }),
  component: Landing,
});

type Status =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; message: string }
  | { kind: "error"; message: string };

function Landing() {
  return (
    <div className="min-h-screen">
      <Nav />
      <Hero />
      <Features />
      <Workflow />
      <Studio />
      <Footer />
    </div>
  );
}

function Nav() {
  return (
    <header className="sticky top-4 z-40 mx-auto flex max-w-6xl items-center justify-between rounded-full px-5 py-3 neo-surface-sm mt-4"
      style={{ width: "calc(100% - 2rem)" }}
    >
      <a href="#top" className="flex items-center gap-2">
        <span className="grid h-9 w-9 place-items-center rounded-full neo-btn-primary">
          <Waves className="h-4 w-4" />
        </span>
        <span className="font-display text-lg font-semibold tracking-tight">VoiceThread</span>
      </a>
      <nav className="hidden items-center gap-7 text-sm text-muted-foreground md:flex">
        <a href="#features" className="hover:text-foreground">Features</a>
        <a href="#workflow" className="hover:text-foreground">How it works</a>
        <a href="#studio" className="hover:text-foreground">Studio</a>
      </nav>
      <a
        href="#studio"
        className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium neo-btn-primary"
      >
        Open studio <ArrowRight className="h-4 w-4" />
      </a>
    </header>
  );
}

function Hero() {
  return (
    <section id="top" className="mx-auto max-w-6xl px-6 pt-20 pb-24 md:pt-28">
      <div className="grid items-center gap-12 md:grid-cols-2">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium text-primary neo-surface-sm">
            <Sparkles className="h-3.5 w-3.5" /> AI content studio for creators
          </span>
          <h1 className="mt-6 font-display text-5xl font-semibold leading-[1.05] tracking-tight md:text-6xl">
            Turn YouTube videos into threads that <span className="text-primary">sound like you</span>.
          </h1>
          <p className="mt-6 max-w-lg text-lg text-muted-foreground">
            VoiceThread learns your writing voice, pulls the transcript from any video, and generates a
            polished social thread in seconds — no more blank-page mornings.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <a href="#studio" className="inline-flex items-center gap-2 px-6 py-3 text-sm font-medium neo-btn-primary">
              Start creating <ArrowRight className="h-4 w-4" />
            </a>
            <a href="#workflow" className="inline-flex items-center gap-2 px-6 py-3 text-sm font-medium neo-btn">
              See how it works
            </a>
          </div>
          <dl className="mt-10 grid grid-cols-3 gap-3 text-center">
            {[
              ["3 steps", "Voice → transcript → thread"],
              ["<10s", "Average generation time"],
              ["Your voice", "Not generic AI copy"],
            ].map(([k, v]) => (
              <div key={k} className="px-3 py-4 neo-surface-sm">
                <dt className="font-display text-lg font-semibold text-foreground">{k}</dt>
                <dd className="mt-1 text-xs text-muted-foreground">{v}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="relative">
          <div className="absolute inset-0 -z-10 rounded-[3rem] neo-surface" />
          <img
            src={heroImg}
            alt="Isometric illustration of a soundwave transforming into text threads"
            width={1024}
            height={1024}
            className="relative mx-auto w-full max-w-lg"
          />
        </div>
      </div>
    </section>
  );
}

function Features() {
  const items = [
    {
      icon: Mic,
      title: "Voice training",
      body: "Paste a few writing samples and VoiceThread builds a fingerprint of your tone, cadence, and quirks.",
    },
    {
      icon: Youtube,
      title: "Transcript extraction",
      body: "Drop any YouTube URL — we fetch clean, timestamped captions ready for rewriting.",
    },
    {
      icon: ScrollText,
      title: "Thread generation",
      body: "Instant multi-post threads for Twitter or LinkedIn, structured to hook, deliver, and close.",
    },
    {
      icon: Wand2,
      title: "Human, not generic",
      body: "Output stays close to your voice — no em-dash soup, no 'let's dive in' openers.",
    },
  ];
  return (
    <section id="features" className="mx-auto max-w-6xl px-6 py-20">
      <div className="max-w-2xl">
        <h2 className="font-display text-4xl font-semibold tracking-tight md:text-5xl">
          Built for creators who want to sound like themselves.
        </h2>
        <p className="mt-4 text-muted-foreground">
          Four quiet, well-crafted tools that replace an afternoon of writing.
        </p>
      </div>
      <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        {items.map(({ icon: Icon, title, body }) => (
          <article key={title} className="p-6 neo-surface">
            <span className="grid h-12 w-12 place-items-center rounded-2xl neo-inset">
              <Icon className="h-5 w-5 text-primary" />
            </span>
            <h3 className="mt-5 font-display text-lg font-semibold">{title}</h3>
            <p className="mt-2 text-sm text-muted-foreground">{body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function Workflow() {
  const steps = [
    {
      n: "01",
      title: "Train your voice",
      body: "Feed VoiceThread 3–5 pieces of writing that represent how you actually sound.",
    },
    {
      n: "02",
      title: "Fetch a transcript",
      body: "Paste a YouTube link. We extract the transcript, cleaned and ready for rewriting.",
    },
    {
      n: "03",
      title: "Generate the thread",
      body: "Pick the platform and get a structured thread you can post — or refine in a click.",
    },
  ];
  return (
    <section id="workflow" className="mx-auto max-w-6xl px-6 py-20">
      <div className="rounded-[2.5rem] p-10 md:p-14 neo-surface">
        <div className="flex flex-col items-start justify-between gap-6 md:flex-row md:items-end">
          <h2 className="max-w-xl font-display text-4xl font-semibold tracking-tight">
            Three steps from a video you like to a thread you'll actually post.
          </h2>
          <span className="text-sm text-muted-foreground">Under 60 seconds, end-to-end.</span>
        </div>
        <ol className="mt-10 grid gap-6 md:grid-cols-3">
          {steps.map((s) => (
            <li key={s.n} className="p-6 neo-inset">
              <span className="font-display text-3xl font-semibold text-primary">{s.n}</span>
              <h3 className="mt-3 font-display text-lg font-semibold">{s.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{s.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function Studio() {
  const [voiceId, setVoiceId] = useState<string | null>(null);
  const [transcript, setTranscript] = useState("");
  const [thread, setThread] = useState<string[] | null>(null);

  return (
    <section id="studio" className="mx-auto max-w-6xl px-6 py-20">
      <div className="max-w-2xl">
        <span className="inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs text-primary neo-surface-sm">
          <Sparkles className="h-3.5 w-3.5" /> Studio
        </span>
        <h2 className="mt-4 font-display text-4xl font-semibold tracking-tight md:text-5xl">
          The studio.
        </h2>
        <p className="mt-4 text-muted-foreground">
          Complete the three steps below in order, or jump straight to any card.
        </p>
      </div>

      <div className="mt-12 grid gap-6 lg:grid-cols-3">
        <VoiceCard onTrained={setVoiceId} voiceId={voiceId} />
        <TranscriptCard onTranscript={setTranscript} transcript={transcript} />
        <GenerateCard
          transcript={transcript}
          voiceId={voiceId}
          onThread={setThread}
        />
      </div>

      <ThreadPreview thread={thread} />
    </section>
  );
}

function StatusBox({ status }: { status: Status }) {
  if (status.kind === "idle") return null;
  if (status.kind === "loading")
    return (
      <div className="mt-4 flex items-center gap-2 rounded-xl px-4 py-3 text-sm text-muted-foreground neo-inset">
        <Loader2 className="h-4 w-4 animate-spin" /> Working on it…
      </div>
    );
  if (status.kind === "success")
    return (
      <div className="mt-4 flex items-start gap-2 rounded-xl px-4 py-3 text-sm neo-inset" style={{ color: "oklch(0.45 0.12 155)" }}>
        <Check className="mt-0.5 h-4 w-4 shrink-0" />
        <span>{status.message}</span>
      </div>
    );
  return (
    <div className="mt-4 flex items-start gap-2 rounded-xl px-4 py-3 text-sm neo-inset text-destructive">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{status.message}</span>
    </div>
  );
}

function CardShell({
  step,
  title,
  desc,
  children,
}: {
  step: string;
  title: string;
  desc: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col p-6 neo-surface">
      <div className="flex items-center gap-3">
        <span className="grid h-9 w-9 place-items-center rounded-full text-xs font-semibold text-primary neo-inset">
          {step}
        </span>
        <h3 className="font-display text-lg font-semibold">{title}</h3>
      </div>
      <p className="mt-2 text-sm text-muted-foreground">{desc}</p>
      <div className="mt-5 flex flex-1 flex-col">{children}</div>
    </div>
  );
}

function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className="w-full resize-none rounded-2xl bg-transparent px-4 py-3 text-sm text-foreground outline-none placeholder:text-muted-foreground neo-inset focus:neo-pressed"
    />
  );
}
function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className="w-full rounded-2xl bg-transparent px-4 py-3 text-sm text-foreground outline-none placeholder:text-muted-foreground neo-inset focus:neo-pressed"
    />
  );
}

function VoiceCard({
  onTrained,
  voiceId,
}: {
  onTrained: (id: string) => void;
  voiceId: string | null;
}) {
  const run = useServerFn(trainVoice);
  const [samples, setSamples] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setStatus({ kind: "loading" });
    try {
      const res = await run({ data: { samples, creatorId: getCreatorId() } });
      onTrained(res.voiceId);
      setStatus({
        kind: "success",
        message: `Voice trained: ${res.stats.tone} · ${res.stats.wordCount} words analysed.`,
      });
    } catch (err) {
      setStatus({ kind: "error", message: err instanceof Error ? err.message : "Something went wrong." });
    }
  }

  return (
    <CardShell
      step="01"
      title="Train your voice"
      desc="Paste 2–3 pieces of writing that represent how you sound."
    >
      <form onSubmit={submit} className="flex flex-1 flex-col">
        <TextArea
          rows={7}
          placeholder="Paste tweets, essay excerpts, or LinkedIn posts…"
          value={samples}
          onChange={(e) => setSamples(e.target.value)}
        />
        <button
          type="submit"
          className="mt-4 inline-flex items-center justify-center gap-2 px-5 py-3 text-sm font-medium neo-btn-primary"
          disabled={status.kind === "loading"}
        >
          <Mic className="h-4 w-4" />
          {voiceId ? "Retrain voice" : "Train voice"}
        </button>
        <StatusBox status={status} />
      </form>
    </CardShell>
  );
}

function TranscriptCard({
  onTranscript,
  transcript,
}: {
  onTranscript: (t: string) => void;
  transcript: string;
}) {
  const run = useServerFn(fetchTranscript);
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setStatus({ kind: "loading" });
    try {
      const res = await run({ data: { url } });
      onTranscript(res.transcript);
      setStatus({ kind: "success", message: `Transcript fetched for video ${res.videoId}.` });
    } catch (err) {
      setStatus({ kind: "error", message: err instanceof Error ? err.message : "Something went wrong." });
    }
  }

  return (
    <CardShell
      step="02"
      title="Fetch the transcript"
      desc="Paste any YouTube URL — we'll extract the captions."
    >
      <form onSubmit={submit} className="flex flex-1 flex-col">
        <TextInput
          type="url"
          placeholder="https://youtube.com/watch?v=…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <TextArea
          rows={5}
          className="mt-3 w-full resize-none rounded-2xl bg-transparent px-4 py-3 text-sm text-foreground outline-none placeholder:text-muted-foreground neo-inset"
          placeholder="Transcript will appear here… (or paste your own)"
          value={transcript}
          onChange={(e) => onTranscript(e.target.value)}
        />
        <button
          type="submit"
          className="mt-4 inline-flex items-center justify-center gap-2 px-5 py-3 text-sm font-medium neo-btn-primary"
          disabled={status.kind === "loading"}
        >
          <Youtube className="h-4 w-4" /> Fetch transcript
        </button>
        <StatusBox status={status} />
      </form>
    </CardShell>
  );
}

function GenerateCard({
  transcript,
  voiceId,
  onThread,
}: {
  transcript: string;
  voiceId: string | null;
  onThread: (t: string[]) => void;
}) {
  const run = useServerFn(generateThread);
  const [platform, setPlatform] = useState<"twitter" | "linkedin">("twitter");
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setStatus({ kind: "loading" });
    try {
      const res = await run({
        data: { transcript, platform, voiceId: voiceId ?? undefined, creatorId: getCreatorId() },
      });
      onThread(res.posts);
      setStatus({ kind: "success", message: `Generated ${res.posts.length} posts for ${res.platform}.` });
    } catch (err) {
      setStatus({ kind: "error", message: err instanceof Error ? err.message : "Something went wrong." });
    }
  }

  return (
    <CardShell
      step="03"
      title="Generate the thread"
      desc="Pick a platform, then generate. Uses your trained voice if available."
    >
      <form onSubmit={submit} className="flex flex-1 flex-col">
        <div className="grid grid-cols-2 gap-2 p-1.5 neo-inset rounded-full">
          {(["twitter", "linkedin"] as const).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPlatform(p)}
              className={`rounded-full px-3 py-2 text-xs font-medium capitalize transition ${
                platform === p ? "neo-btn-primary" : "text-muted-foreground"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
        <div className="mt-4 rounded-2xl px-4 py-3 text-xs text-muted-foreground neo-inset">
          <div className="flex items-center justify-between">
            <span>Voice</span>
            <span className={voiceId ? "text-primary" : "text-muted-foreground"}>
              {voiceId ? "trained ✓" : "not trained"}
            </span>
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span>Transcript</span>
            <span className={transcript ? "text-primary" : "text-muted-foreground"}>
              {transcript ? `${transcript.length} chars` : "empty"}
            </span>
          </div>
        </div>
        <button
          type="submit"
          className="mt-4 inline-flex items-center justify-center gap-2 px-5 py-3 text-sm font-medium neo-btn-primary disabled:opacity-60"
          disabled={status.kind === "loading" || !transcript}
        >
          <Sparkles className="h-4 w-4" /> Generate thread
        </button>
        <StatusBox status={status} />
      </form>
    </CardShell>
  );
}

function ThreadPreview({ thread }: { thread: string[] | null }) {
  if (!thread) return null;
  const full = thread.join("\n\n");
  return (
    <div className="mt-8 p-8 neo-surface">
      <div className="flex items-center justify-between">
        <h3 className="font-display text-xl font-semibold">Your thread</h3>
        <button
          onClick={() => navigator.clipboard.writeText(full)}
          className="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium neo-btn"
        >
          <Copy className="h-3.5 w-3.5" /> Copy all
        </button>
      </div>
      <ol className="mt-6 space-y-3">
        {thread.map((post, i) => (
          <li key={i} className="rounded-2xl p-4 text-sm leading-relaxed neo-inset">
            {post}
          </li>
        ))}
      </ol>
    </div>
  );
}

function Footer() {
  return (
    <footer className="mx-auto mt-10 max-w-6xl px-6 pb-16">
      <div className="flex flex-col items-start justify-between gap-6 rounded-3xl px-8 py-8 neo-surface-sm md:flex-row md:items-center">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-full neo-btn-primary">
            <Waves className="h-4 w-4" />
          </span>
          <div>
            <div className="font-display text-base font-semibold">VoiceThread</div>
            <div className="text-xs text-muted-foreground">Your voice, at the speed of publishing.</div>
          </div>
        </div>
        <div className="text-xs text-muted-foreground">
          © {new Date().getFullYear()} VoiceThread — crafted for creators.
        </div>
      </div>
    </footer>
  );
}
