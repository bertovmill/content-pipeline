# Stage 0: Intro Screens Reference

`00_create_intro.py` — run last, after Stages 2 and 6.

## Three Intro Screens

| Screen | Duration | Visual | Voiceover |
|---|---|---|---|
| Branded card | Matches TTS | Circle-cropped headshot, name, LinkedIn QR | AI-generated welcome + video overview (Claude writes script, ElevenLabs speaks it) |
| Title screen | Matches TTS | Large title text + "Tutorial" label + date | AI reads the video title aloud |
| TOC screen | Matches TTS | "What We'll Cover" + numbered topics | AI reads all chapter topics aloud |

**Clip durations are driven by TTS length** — not hardcoded. Longer topic lists = longer TOC clip.

## How It Works

1. Reads title from `youtube.md` (first `# ` line)
2. Calls Claude with the first 60 captions to generate 8 accurate chapter topics (JSON array)
3. Calls Claude to write a 2-3 sentence branded card script ("Hey everyone, welcome back! Today we're...")
4. Generates ElevenLabs TTS for all 3 slides
5. Renders each PNG frame, creates a still video clip matching TTS duration
6. Concatenates: branded + title + TOC + main `output.mp4` → `output_with_intro.mp4`

## Key Functions

- `extract_toc_topics(n=8)` — Claude reads captions.json, returns accurate chapter titles. No hardcoded overrides.
- `generate_branded_voiceover(title, topics)` — Claude writes the welcome script
- `generate_tts(text, output_path)` — ElevenLabs TTS, returns duration in seconds
- `_make_clip_with_tts(frame_png, tts_mp3, output_mp4)` — combines still frame + TTS audio into a clip
- `_add_silent_audio(video_path)` — fallback only; detects existing audio and skips if already present

## Design System

- Background: near-black `#0d0d1a` with subtle gradient
- Accent: indigo `#4f46e5`
- Fonts: SF Pro (SFNS.ttf), Helvetica fallback
- Resolution: 3456x2234 (matches Retina screen recordings)

## Dependencies

```bash
pip install qrcode pillow anthropic elevenlabs
```

Files needed in project root:
- `berto-mill.png` — headshot (copied from reference implementation)
- `youtube.md` — Stage 6 output
- `captions.json` — Stage 2 output

## Tmp Files Cleaned Up

`tmp_intro_branded.png`, `tmp_intro_title.png`, `tmp_intro_toc.png`,  
`tmp_clip_branded.mp4`, `tmp_clip_title.mp4`, `tmp_clip_toc.mp4`,  
`tmp_tts_branded.mp3`, `tmp_tts_title.mp3`, `tmp_tts_toc.mp3`
