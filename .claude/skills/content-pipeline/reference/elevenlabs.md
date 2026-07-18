# ElevenLabs Features Reference

## Stage 3: Main Narration Audio

- `convert_with_timestamps()` — word-level timing saved per clip to `audio/timestamps/`
- `previous_text` / `next_text` — context continuity so narration flows between clips
- `music.compose()` — auto-generates ~3-min background music if `MUSIC_TRACK_PATH` not set
- `text_to_sound_effects.convert()` — whoosh SFX between every Nth clip. Prompt: "soft cinematic whoosh transition, smooth and airy, like a quick wind gust", 0.5s duration. Delete `audio/sfx/transition.mp3` to regenerate.

## Stage 7: SRT Captions

- `speech_to_text.convert()` — transcribes all TTS clips into `captions.srt`

## Stage 0: Intro Voiceover

- `text_to_speech.convert()` — generates voiceover for branded card, title, and TOC slides
- Same voice ID (`ELEVENLABS_VOICE_ID`) as main narration for consistency
- Duration of each slide is set by the TTS output length (not hardcoded)

## Pronunciation Dictionary

- Requires `pronunciation_dictionaries_write` permission on the API key
- Fails gracefully with a warning if permission is missing
- Used to improve pronunciation of technical terms (e.g., "npm", "ffmpeg")

## Config Variables

| Variable | Where set | Effect |
|---|---|---|
| `ELEVENLABS_VOICE_ID` | `.env` | Voice used for all TTS across all stages |
| `MUSIC_TRACK_PATH` | `.env` | Path to custom .mp3; auto-generates if empty |
| `MUSIC_VOLUME` | `config.py` | Background music mix level (0.15 = 15%) |
| `SFX_VOLUME` | `config.py` | Transition whoosh volume |
| `SFX_FREQUENCY` | `config.py` | Insert SFX every N segments |
