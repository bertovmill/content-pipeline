import os
import json
import base64
import subprocess
import shutil
from pathlib import Path
from elevenlabs import ElevenLabs
from elevenlabs.types import PronunciationDictionaryVersionLocator
import config

# Technical terms that TTS models commonly mispronounce
PRONUNCIATION_RULES = [
    {"type": "alias", "string_to_replace": "LangSmith", "alias": "Lang Smith"},
    {"type": "alias", "string_to_replace": "LangGraph", "alias": "Lang Graph"},
    {"type": "alias", "string_to_replace": "LangChain", "alias": "Lang Chain"},
    {"type": "alias", "string_to_replace": "GLM", "alias": "G L M"},
    {"type": "alias", "string_to_replace": "npm", "alias": "N P M"},
    {"type": "alias", "string_to_replace": "MCP", "alias": "M C P"},
    {"type": "alias", "string_to_replace": "tsx", "alias": "T S X"},
    {"type": "alias", "string_to_replace": "localhost", "alias": "local host"},
]


def tts_path_for_frame(frame_relative: str, tts_dir: str) -> str:
    stem = Path(frame_relative).stem
    return os.path.join(tts_dir, f"{stem}.mp3")


def timestamps_path_for_frame(frame_relative: str, timestamps_dir: str) -> str:
    stem = Path(frame_relative).stem
    return os.path.join(timestamps_dir, f"{stem}.json")


def mixed_path_for_frame(frame_relative: str, mixed_dir: str) -> str:
    stem = Path(frame_relative).stem
    return os.path.join(mixed_dir, f"{stem}.mp3")


def get_or_create_pronunciation_dict(client: ElevenLabs) -> PronunciationDictionaryVersionLocator | None:
    """Create a pronunciation dictionary for technical terms. Returns locator or None on failure."""
    try:
        result = client.pronunciation_dictionaries.create_from_rules(
            name="tutorial-tech-terms",
            rules=PRONUNCIATION_RULES,
        )
        print(f"  Created pronunciation dict: {result.id} v{result.version_id}")
        return PronunciationDictionaryVersionLocator(
            pronunciation_dictionary_id=result.id,
            version_id=result.version_id,
        )
    except Exception as e:
        print(f"  Warning: could not create pronunciation dict: {e}")
        return None


def generate_tts(
    text: str,
    output_path: str,
    timestamps_path: str,
    client: ElevenLabs,
    voice_id: str,
    previous_text: str = "",
    next_text: str = "",
    pronunciation_locator: PronunciationDictionaryVersionLocator | None = None,
) -> None:
    """Generate TTS with timestamps. Skips if output already exists."""
    if os.path.exists(output_path):
        return
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    os.makedirs(os.path.dirname(timestamps_path), exist_ok=True)

    kwargs = dict(
        voice_id=voice_id,
        text=text,
        model_id="eleven_multilingual_v2",
        previous_text=previous_text or None,
        next_text=next_text or None,
    )
    if pronunciation_locator:
        kwargs["pronunciation_dictionary_locators"] = [pronunciation_locator]

    response = client.text_to_speech.convert_with_timestamps(**kwargs)

    audio_bytes = base64.b64decode(response.audio_base_64)
    with open(output_path, "wb") as f:
        f.write(audio_bytes)

    if response.alignment:
        with open(timestamps_path, "w") as f:
            json.dump({
                "characters": response.alignment.characters,
                "start_times": response.alignment.character_start_times_seconds,
                "end_times": response.alignment.character_end_times_seconds,
            }, f, indent=2)


def generate_sfx(output_path: str, client: ElevenLabs) -> None:
    """Generate a short transition sound effect. Skips if output exists."""
    if os.path.exists(output_path):
        return
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    chunks = client.text_to_sound_effects.convert(
        text="soft subtle tech transition whoosh",
        duration_seconds=0.8,
    )
    with open(output_path, "wb") as f:
        for chunk in chunks:
            f.write(chunk)


def generate_background_music(output_path: str, client: ElevenLabs, duration_ms: int = 180000) -> None:
    """Generate background music via ElevenLabs. Skips if output exists."""
    if os.path.exists(output_path):
        return
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    print(f"  Generating background music (~{duration_ms // 1000}s)...")
    chunks = client.music.compose(
        prompt="calm lo-fi background music for a developer tutorial, minimal beats, no vocals, tech vibe",
        music_length_ms=duration_ms,
    )
    with open(output_path, "wb") as f:
        for chunk in chunks:
            f.write(chunk)


def _get_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def mix_audio(tts_path: str, music_path: str, output_path: str, music_volume: float,
              music_offset: float = 0.0) -> None:
    """Mix TTS with background music starting at music_offset. If no music, copies TTS as-is."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    if not music_path or not os.path.exists(music_path):
        shutil.copy2(tts_path, output_path)
        return
    cmd = [
        "ffmpeg", "-y",
        "-i", tts_path,
        "-stream_loop", "-1", "-ss", f"{music_offset:.3f}", "-i", music_path,
        "-filter_complex",
        f"[1:a]volume={music_volume}[music];[0:a][music]amix=inputs=2:duration=first[out]",
        "-map", "[out]",
        "-c:a", "libmp3lame",
        output_path,
    ]
    result = subprocess.run(cmd, check=False, capture_output=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, stderr=result.stderr.decode()
        )


def main():
    client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)

    with open(config.CAPTIONS_FILE, "r") as f:
        captions = json.load(f)

    valid_captions = [e for e in captions if not e["caption"].startswith("ERROR:")]

    # Create pronunciation dictionary once for the whole run
    print("Setting up pronunciation dictionary...")
    pronunciation_locator = get_or_create_pronunciation_dict(client)

    # Generate background music if no music track configured
    music_path = config.MUSIC_TRACK_PATH
    if not music_path or not os.path.exists(music_path):
        music_path = config.AUDIO_MUSIC_FILE
        print("No MUSIC_TRACK_PATH set — generating background music with ElevenLabs...")
        generate_background_music(music_path, client)

    sfx_path = os.path.join(config.AUDIO_SFX_DIR, "transition.mp3")
    print("Generating transition SFX...")
    generate_sfx(sfx_path, client)

    print(f"Processing {len(valid_captions)} captions...")
    music_offset = 0.0
    for i, entry in enumerate(valid_captions):
        frame = entry["frame"]
        caption = entry["caption"]

        previous_text = valid_captions[i - 1]["caption"] if i > 0 else ""
        next_text = valid_captions[i + 1]["caption"] if i < len(valid_captions) - 1 else ""

        tts_out = tts_path_for_frame(frame, config.AUDIO_TTS_DIR)
        ts_out = timestamps_path_for_frame(frame, config.TIMESTAMPS_DIR)
        mixed_out = mixed_path_for_frame(frame, config.AUDIO_MIXED_DIR)

        generate_tts(
            caption, tts_out, ts_out, client, config.ELEVENLABS_VOICE_ID,
            previous_text=previous_text,
            next_text=next_text,
            pronunciation_locator=pronunciation_locator,
        )
        tts_dur = _get_duration(tts_out)
        if not os.path.exists(mixed_out):
            mix_audio(tts_out, music_path, mixed_out, config.MUSIC_VOLUME, music_offset)
        music_offset += tts_dur
        print(f"  [{i + 1}/{len(valid_captions)}] {os.path.basename(frame)} done")

    print("Audio generation complete.")


if __name__ == "__main__":
    main()
