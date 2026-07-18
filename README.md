# Content Pipeline

Turns a raw `.mov` screen recording into a full content package: a narrated YouTube video with a branded intro, animated concept cut scenes, an SRT caption file, a thumbnail, a blog article, and YouTube metadata.

It runs as a [Claude Code](https://claude.com/claude-code) skill (shipped in `.claude/skills/content-pipeline/`) backed by an idempotent, multi-stage Python pipeline.

## What it produces

| Output | Stage | Description |
|---|---|---|
| `content-ideas.md` | I | Ranked trending-AI-tool ideas to record next |
| `frames/` | 1 | Deduplicated screenshots from the recording |
| `captions.json` | 2 | Claude Vision narration per frame |
| `output.mp4` | 3+4 | Composed video with AI narration and music |
| `thumbnail.png` | 5 | 1280x720 YouTube thumbnail |
| `youtube.md` | 6 | Title, description, and tags |
| `captions.srt` | 7 | SRT subtitles |
| `article.md` | 8 | Full tutorial blog post |
| `output_with_intro.mp4` | 0 | Final video with branded intro |

## Pipeline stages

Run in order (each stage is idempotent, so you can re-run safely):

1. `ideate.py` — pick what to record based on trending signals
2. `01_extract_frames.py` — extract and dedupe frames
3. `02_caption_frames.py` — Claude Vision writes first-person narration per frame
4. `03_generate_audio.py` — ElevenLabs TTS + background music
5. `04_compose_video.py` — cut and compose the video
6. `05_create_thumbnail.py` — build the YouTube thumbnail
7. `06_youtube_metadata.py` — generate title, description, tags
8. `07_generate_srt.py` — transcribe audio to SRT
9. `08_generate_article.py` — write the blog post
10. `00_create_intro.py` — prepend the branded intro (run last)

See `.claude/skills/content-pipeline/SKILL.md` and the `reference/` docs for full details.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in your keys
```

Required keys (see `.env.example`):

- `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` — text-to-speech and transcription
- `AI_GATEWAY_API_KEY` — Claude access for captioning, ideation, and writing

## Notes

- Media files (`.mov`, `.mp4`, generated `frames/`, `audio/`, etc.) are gitignored — they are large and regenerated per run.
- Never commit your real `.env`; it holds API keys.
