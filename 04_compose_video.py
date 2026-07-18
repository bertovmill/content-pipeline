import hashlib
import os
import json
import subprocess
from pathlib import Path
import config


def get_audio_duration(audio_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def get_video_duration(video_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def file_md5(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def get_frame_timestamp_map(raw_dir: str, frames_dir: str, interval_seconds: int) -> dict:
    """Map kept frame filenames to their source video start timestamps.

    Matches frames/ PNGs back to frames_raw/ originals via MD5, then converts
    the raw frame number to a video timestamp: ts = (raw_num - 1) * interval.
    """
    raw_hash_to_num: dict[str, int] = {}
    for raw_path in sorted(Path(raw_dir).glob("raw_*.png")):
        num = int(raw_path.stem.split("_")[1])
        raw_hash_to_num[file_md5(str(raw_path))] = num

    mapping: dict[str, float] = {}
    for kept_path in sorted(Path(frames_dir).glob("*.png")):
        h = file_md5(str(kept_path))
        if h in raw_hash_to_num:
            num = raw_hash_to_num[h]
            mapping[kept_path.name] = (num - 1) * interval_seconds
    return mapping


def cut_video_segment(
    video_path: str,
    start_time: float,
    end_time: float,
    audio_duration: float,
    output_path: str,
) -> None:
    """Cut a segment from video_path and speed-adjust so duration matches audio_duration."""
    segment_duration = end_time - start_time
    # pts_factor < 1 speeds up; > 1 slows down
    pts_factor = audio_duration / segment_duration

    result = subprocess.run([
        "ffmpeg", "-y",
        "-ss", f"{start_time:.3f}",
        "-to", f"{end_time:.3f}",
        "-i", video_path,
        "-vf", f"setpts={pts_factor:.6f}*PTS",
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        output_path,
    ], check=False, capture_output=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, "ffmpeg", stderr=result.stderr.decode())


def build_audio_concat_file(audio_paths: list, output_path: str, sfx_path: str = "") -> None:
    lines = []
    for i, ap in enumerate(audio_paths):
        lines.append(f"file '{ap}'")
        if sfx_path and i < len(audio_paths) - 1:
            lines.append(f"file '{sfx_path}'")
    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def compose_video_from_recording(
    video_path: str,
    raw_dir: str,
    frames_dir: str,
    mixed_audio_dir: str,
    output_path: str,
    tmp_dir: str,
) -> None:
    """Build final MP4 from speed-adjusted video segments + AI narration audio."""
    os.makedirs(tmp_dir, exist_ok=True)

    with open(config.CAPTIONS_FILE, "r") as f:
        captions = json.load(f)

    print("Mapping kept frames to video timestamps...")
    timestamp_map = get_frame_timestamp_map(raw_dir, frames_dir, config.FRAME_INTERVAL_SECONDS)
    if not timestamp_map:
        raise RuntimeError(
            f"Could not map any frames — ensure {raw_dir} contains the original raw_*.png files"
        )

    video_total_duration = get_video_duration(video_path)

    entries = []
    for entry in captions:
        if entry["caption"].startswith("ERROR:"):
            continue
        stem = Path(entry["frame"]).stem
        frame_name = f"{stem}.png"
        audio_abs = os.path.join(mixed_audio_dir, f"{stem}.mp3")
        if not os.path.exists(audio_abs) or frame_name not in timestamp_map:
            continue
        entries.append({
            "stem": stem,
            "audio": audio_abs,
            "start_ts": timestamp_map[frame_name],
        })

    for i, entry in enumerate(entries):
        entry["end_ts"] = entries[i + 1]["start_ts"] if i + 1 < len(entries) else video_total_duration

    segment_paths = []
    audio_paths = []

    for i, entry in enumerate(entries):
        audio_dur = get_audio_duration(entry["audio"])
        seg_path = os.path.join(tmp_dir, f"seg_{i:04d}.mp4")
        print(
            f"  Segment {i + 1}/{len(entries)}: "
            f"[{entry['start_ts']:.1f}s – {entry['end_ts']:.1f}s] "
            f"-> {audio_dur:.1f}s narration"
        )
        cut_video_segment(video_path, entry["start_ts"], entry["end_ts"], audio_dur, seg_path)
        segment_paths.append(seg_path)
        audio_paths.append(entry["audio"])

    seg_concat = os.path.join(tmp_dir, "concat_segs.txt")
    with open(seg_concat, "w") as f:
        for sp in segment_paths:
            f.write(f"file '{sp}'\n")

    audio_concat = os.path.join(tmp_dir, "concat_audio.txt")
    sfx_path = os.path.join(config.AUDIO_SFX_DIR, "transition.mp3")
    build_audio_concat_file(
        audio_paths, audio_concat,
        sfx_path=sfx_path if os.path.exists(sfx_path) else "",
    )

    video_only = os.path.join(tmp_dir, "video_only.mp4")
    audio_full = os.path.join(tmp_dir, "audio_full.aac")

    print("Concatenating video segments...")
    result = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", seg_concat,
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        video_only,
    ], check=False, capture_output=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, "ffmpeg", stderr=result.stderr.decode())

    print("Concatenating audio...")
    result = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", audio_concat,
        "-c:a", "aac", audio_full,
    ], check=False, capture_output=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, "ffmpeg", stderr=result.stderr.decode())

    print("Merging video + audio...")
    result = subprocess.run([
        "ffmpeg", "-y", "-i", video_only, "-i", audio_full,
        "-c:v", "copy", "-c:a", "aac", "-shortest",
        output_path,
    ], check=False, capture_output=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, "ffmpeg", stderr=result.stderr.decode())


# ---------------------------------------------------------------------------
# Slideshow fallback (original behaviour)
# ---------------------------------------------------------------------------

def build_video_concat_file(frame_paths: list, durations: list, output_path: str) -> None:
    lines = []
    for frame, dur in zip(frame_paths, durations):
        lines.append(f"file '{frame}'")
        lines.append(f"duration {dur}")
    lines.append(f"file '{frame_paths[-1]}'")
    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def compose_video_slideshow(
    frames_dir: str,
    mixed_audio_dir: str,
    output_path: str,
    tmp_dir: str,
) -> None:
    """Build final MP4 from still frames (slideshow) + mixed audio."""
    os.makedirs(tmp_dir, exist_ok=True)

    with open(config.CAPTIONS_FILE, "r") as f:
        captions = json.load(f)

    frame_paths = []
    audio_paths = []
    durations = []

    for entry in captions:
        if entry["caption"].startswith("ERROR:"):
            continue
        stem = Path(entry["frame"]).stem
        frame_abs = os.path.join(frames_dir, f"{stem}.png")
        audio_abs = os.path.join(mixed_audio_dir, f"{stem}.mp3")
        if not os.path.exists(frame_abs) or not os.path.exists(audio_abs):
            continue
        dur = get_audio_duration(audio_abs)
        frame_paths.append(frame_abs)
        audio_paths.append(audio_abs)
        durations.append(dur)

    video_concat = os.path.join(tmp_dir, "concat_video.txt")
    audio_concat = os.path.join(tmp_dir, "concat_audio.txt")
    video_only = os.path.join(tmp_dir, "video_only.mp4")
    audio_full = os.path.join(tmp_dir, "audio_full.aac")

    build_video_concat_file(frame_paths, durations, video_concat)
    sfx_path = os.path.join(config.AUDIO_SFX_DIR, "transition.mp3")
    build_audio_concat_file(
        audio_paths, audio_concat,
        sfx_path=sfx_path if os.path.exists(sfx_path) else "",
    )

    result = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", video_concat,
        "-vsync", "vfr", "-pix_fmt", "yuv420p", "-c:v", "libx264",
        video_only,
    ], check=False, capture_output=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, "ffmpeg", stderr=result.stderr.decode())

    result = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", audio_concat,
        "-c:a", "aac", audio_full,
    ], check=False, capture_output=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, "ffmpeg", stderr=result.stderr.decode())

    result = subprocess.run([
        "ffmpeg", "-y", "-i", video_only, "-i", audio_full,
        "-c:v", "copy", "-c:a", "aac", "-shortest",
        output_path,
    ], check=False, capture_output=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, "ffmpeg", stderr=result.stderr.decode())


def find_source_video(project_dir: str) -> str:
    # Prefer the pre-sped-up video created by Stage 1 if it exists
    sped_up = config.SPED_UP_VIDEO
    if os.path.exists(sped_up):
        return sped_up
    matches = sorted(Path(project_dir).glob("*.mov"))
    if not matches:
        raise FileNotFoundError(f"No .mov file found in {project_dir}")
    return str(matches[0])


def main():
    tmp_dir = os.path.join(config.PROJECT_DIR, "tmp_compose")
    print("Composing final video...")

    try:
        video_path = find_source_video(config.PROJECT_DIR)
        raw_dir = config.RAW_FRAMES_DIR
        if not os.path.isdir(raw_dir) or not list(Path(raw_dir).glob("raw_*.png")):
            raise FileNotFoundError(f"Raw frames not found in {raw_dir}")
        print(f"Using screen recording: {Path(video_path).name}")
        compose_video_from_recording(
            video_path, raw_dir, config.FRAMES_DIR,
            config.AUDIO_MIXED_DIR, config.OUTPUT_VIDEO, tmp_dir,
        )
    except (FileNotFoundError, RuntimeError) as e:
        print(f"Falling back to slideshow mode ({e})")
        compose_video_slideshow(config.FRAMES_DIR, config.AUDIO_MIXED_DIR, config.OUTPUT_VIDEO, tmp_dir)

    print(f"Done. Output: {config.OUTPUT_VIDEO}")


if __name__ == "__main__":
    main()
