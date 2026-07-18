---
name: content-pipeline
description: Use when turning a screen recording into multiple content formats — YouTube video with branded intro screens, SRT captions, thumbnail, blog article with screenshots, and YouTube metadata.
---

# Content Pipeline

Converts a raw screen recording (`.mov` from QuickTime, `.webm` from the walkthrough app's /record page) into a full content package using a 9-stage idempotent Python pipeline. Reference implementation: `/Users/bertomill/setting-up-langchain-tracing-vid/`.

For detailed docs on specific stages, see the `reference/` files below.

## What It Produces

| Output | Stage | Description |
|---|---|---|
| `content-ideas.md` | I | Ranked trending-AI-tool ideas to record next (runs before recording) |
| `frames/` | 1 | Deduplicated PNG screenshots (3x speed source) |
| `captions.json` | 2 | Claude Vision narration per frame |
| `output.mp4` | 3+4 | Composed video with AI narration and music |
| `thumbnail.png` | 5 | 1280x720 YouTube thumbnail |
| `youtube.md` | 6 | Title (3 A/B options), description, timestamps, tags |
| `captions.srt` | 7 | SRT subtitle file for YouTube |
| `article.md` | 8 | Full tutorial blog post with embedded screenshots |
| `output_with_intro.mp4` | 0 | Final delivery video: branded intro + main content |

## Stages

I. **`ideate.py`** — run FIRST, before you record. Picks what to make a video about. Gathers free momentum signals (Hacker News points, GitHub Trending stars-this-week velocity, Reddit hot), has Claude distill them into candidate AI tools, measures search demand via Google autocomplete (keyless), and ranks by `demand × momentum` (`final = sqrt(demand × momentum)`) → `content-ideas.md`. See `reference/ideation.md`.
1. **`01_extract_frames.py`** — creates a `source_3x.mp4` (3x speed, see `SOURCE_SPEED_MULTIPLIER` in config), then extracts frames every 10s and deduplicates idle screens
2. **`02_caption_frames.py`** — Claude Vision captions each frame as tutorial narration
3. **`03_generate_audio.py`** — ElevenLabs TTS, auto-generated background music, SFX transitions
4. **`04_compose_video.py`** — cuts segments from `source_3x.mp4` and composes with narration audio
5. **`05_create_thumbnail.py`** — Claude extracts company names, Clearbit fetches logos, Pillow composes
6. **`06_youtube_metadata.py`** — Claude generates title options, description, timestamps, tags
7. **`07_generate_srt.py`** — ElevenLabs STT transcribes all audio clips into `captions.srt`
8. **`08_generate_article.py`** — Claude writes full blog post from captions as `article.md`
0. **`00_create_intro.py`** — run LAST; generates ElevenLabs voiceover for all 3 intro slides, then prepends to `output.mp4` → `output_with_intro.mp4`. See `reference/stage-0-intro.md`.

## Setup

```bash
# Copy scripts from reference implementation to new project dir
# Copy .mov recording to project dir
set -a && source .env && set +a
```

`.env` keys needed:
```
AI_GATEWAY_API_KEY=...        # Vercel AI Gateway for Claude (Stages 2, 5, 6, 8, 0)
ANTHROPIC_API_KEY=...         # Fallback if no AI Gateway key
ELEVENLABS_API_KEY=...        # ElevenLabs (Stages 3, 7, 0)
ELEVENLABS_VOICE_ID=s3TPKV1kjDlVtZbl4Ksh
MUSIC_TRACK_PATH=             # Optional: custom .mp3
```

## Running (in order)

```bash
python3 ideate.py              # ~1 min → content-ideas.md (pick your topic, then record)
python3 01_extract_frames.py   # ~3 min (creates source_3x.mp4 first)
python3 02_caption_frames.py   # ~5 min
python3 03_generate_audio.py   # ~15 min
python3 04_compose_video.py    # ~3 min → output.mp4
python3 05_create_thumbnail.py # ~1 min → thumbnail.png
python3 06_youtube_metadata.py # ~1 min → youtube.md
python3 07_generate_srt.py     # ~5 min → captions.srt
python3 08_generate_article.py # ~1 min → article.md
python3 00_create_intro.py     # ~3 min → output_with_intro.mp4 (upload this)
```

## Idempotency

Every stage skips already-completed work. Re-run safely. If Stage 3 crashes, delete 0-byte files in `audio/tts/` and `audio/mixed/` first.

## Key Config (`config.py`)

| Variable | Default | Effect |
|---|---|---|
| `SOURCE_SPEED_MULTIPLIER` | 3.0 | Pre-speeds the recording before frame extraction. Reduces a 30-min raw recording to ~10-min of footage in the final video. Set to 1.0 to disable. |
| `FRAME_INTERVAL_SECONDS` | 10 | Frame sampling rate |
| `SIMILARITY_THRESHOLD` | 0.95 | Idle frame removal aggressiveness |
| `MUSIC_VOLUME` | 0.15 | Background music level |
| `SFX_FREQUENCY` | 8 | Insert SFX whoosh every N segments |
| `CLAUDE_MODEL` | `anthropic/claude-sonnet-4.6` | Model for all Claude calls |

## Common Issues

- **`.mov` Unicode filename**: macOS inserts U+202F before "AM" — use `Path.glob("*.mov")` or Python to copy
- **0-byte TTS files**: Delete from `audio/tts/` and `audio/mixed/` before re-running Stage 3
- **Retina recordings**: Stage 2 auto-downsizes frames to 1280px
- **Pronunciation dict 401**: Enable `pronunciation_dictionaries_write` on ElevenLabs API key
- **New project setup**: Copy all `.py` files + `config.py` + `.env` + `berto-mill.png` from reference implementation
- **Clearbit logos dead**: Clearbit was acquired by HubSpot and the free logo API is gone. Stage 5 now uses Google's favicon service (`www.google.com/s2/favicons?sz=128&domain=...`) — no API key required. Favicons smaller than 32px are discarded as unknown-domain fallbacks.
- **Thumbnail wrong title**: Stage 5 reads the title from `youtube.md` — run Stage 6 first. The old hardcoded title bug has been fixed.

## Ideation Notes (`ideate.py`)

- **No new API keys** — HN, GitHub Trending, and Google autocomplete are all keyless. Reuses `AI_GATEWAY_API_KEY` for the Claude ranking calls.
- **Reddit is best-effort** — Reddit now blocks server IPs without OAuth (403). The stage degrades gracefully; HN + GitHub still yield strong candidates. Add Reddit OAuth creds later if you want that signal.
- **GitHub** — scrapes the public Trending page for stars-this-week velocity (the real "trending" signal). Set optional `GITHUB_TOKEN` to switch to authenticated new-repo search instead.
- **Demand proxy** — Google autocomplete relevance stands in for search volume. It also catches namespace collisions (e.g. `strix` → "strixhaven" = no real tool demand). Ahrefs Keywords Explorer would be more precise but requires a paid API plan (the connected MCP account returns "Insufficient plan").
- Re-run with `python3 ideate.py --refresh` to regenerate.

## Reference Files

- `reference/ideation.md` — detailed ideation-stage docs (sources, scoring, tuning)
- `reference/stage-0-intro.md` — detailed Stage 0 intro screen + voiceover docs
- `reference/elevenlabs.md` — ElevenLabs features used across the pipeline
