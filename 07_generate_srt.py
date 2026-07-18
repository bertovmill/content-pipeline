import os
import json
import glob
import subprocess
from pathlib import Path
from elevenlabs import ElevenLabs
import config


def format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def get_audio_duration(audio_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def transcribe_audio(audio_path: str, client: ElevenLabs) -> list[dict]:
    """Transcribe audio file, returning list of word-level segments with timing."""
    with open(audio_path, "rb") as f:
        response = client.speech_to_text.convert(
            model_id="scribe_v1",
            file=f,
            timestamps_granularity="word",
        )
    words = []
    if response.words:
        for w in response.words:
            if w.type == "word":
                words.append({
                    "text": w.text,
                    "start": w.start,
                    "end": w.end,
                })
    return words


def words_to_srt_blocks(words: list[dict], time_offset: float, index_start: int, max_words: int = 8) -> list[str]:
    """Group words into subtitle blocks of max_words each."""
    blocks = []
    i = 0
    idx = index_start
    while i < len(words):
        group = words[i:i + max_words]
        start = group[0]["start"] + time_offset
        end = group[-1]["end"] + time_offset
        text = " ".join(w["text"] for w in group)
        blocks.append(f"{idx}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{text}\n")
        i += max_words
        idx += 1
    return blocks, idx


def main():
    client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)

    mixed_paths = sorted(glob.glob(os.path.join(config.AUDIO_MIXED_DIR, "*.mp3")))
    if not mixed_paths:
        print(f"No mixed audio found in {config.AUDIO_MIXED_DIR}. Run 03_generate_audio.py first.")
        return

    all_blocks = []
    idx = 1
    time_offset = 0.0

    print(f"Transcribing {len(mixed_paths)} audio clips...")
    for i, audio_path in enumerate(mixed_paths, start=1):
        duration = get_audio_duration(audio_path)
        print(f"  [{i}/{len(mixed_paths)}] {Path(audio_path).name} ({duration:.1f}s)")

        words = transcribe_audio(audio_path, client)
        if words:
            new_blocks, idx = words_to_srt_blocks(words, time_offset, idx)
            all_blocks.extend(new_blocks)

        time_offset += duration

    with open(config.SRT_FILE, "w") as f:
        f.write("\n".join(all_blocks))

    print(f"Done. {config.SRT_FILE} ({len(all_blocks)} subtitle blocks, {time_offset:.1f}s total)")


if __name__ == "__main__":
    main()
