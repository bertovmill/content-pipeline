import subprocess
import os
import glob
import shutil
from pathlib import Path
import numpy as np
from PIL import Image
import config


def frames_are_similar(img1_path: str, img2_path: str, threshold: float) -> bool:
    """Return True if two frames differ by less than (1 - threshold) on average."""
    arr1 = np.array(Image.open(img1_path).convert("RGB"), dtype=np.float32)
    arr2 = np.array(Image.open(img2_path).convert("RGB"), dtype=np.float32)
    mean_diff = np.abs(arr1 - arr2).mean() / 255.0
    return bool((1.0 - mean_diff) >= threshold)


def extract_raw_frames(video_path: str, output_dir: str, interval_seconds: int) -> int:
    """Extract one frame every interval_seconds using ffmpeg. Returns frame count."""
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"fps=1/{interval_seconds}",
        "-q:v", "2",
        f"{output_dir}/raw_%04d.png",
    ]
    result = subprocess.run(cmd, check=False, capture_output=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, stderr=result.stderr.decode()
        )
    return len(glob.glob(f"{output_dir}/raw_*.png"))


def dedup_frames(raw_dir: str, output_dir: str, threshold: float) -> int:
    """Copy non-duplicate frames to output_dir with sequential numbering. Returns kept count."""
    os.makedirs(output_dir, exist_ok=True)
    raw_frames = sorted(glob.glob(f"{raw_dir}/raw_*.png"))
    kept = []
    for frame_path in raw_frames:
        if not kept or not frames_are_similar(kept[-1], frame_path, threshold):
            kept.append(frame_path)
    for i, src in enumerate(kept, start=1):
        dst = os.path.join(output_dir, f"{i:04d}.png")
        shutil.copy2(src, dst)
    return len(kept)


def create_sped_up_video(source_path: str, output_path: str, speed: float) -> None:
    """Create a speed-multiplied version of the source video (no audio)."""
    pts_factor = 1.0 / speed
    cmd = [
        "ffmpeg", "-y", "-i", source_path,
        "-vf", f"setpts={pts_factor:.6f}*PTS",
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        output_path,
    ]
    result = subprocess.run(cmd, check=False, capture_output=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, stderr=result.stderr.decode()
        )


def find_source_video(project_dir: str) -> str:
    """Find the source recording (.mov from QuickTime, .webm from the in-app
    recorder), handling macOS unicode spaces in filename. Deliberately excludes
    .mp4 — the pipeline writes source_3x.mp4/output.mp4 into the same dir.
    """
    matches = sorted(
        p for ext in ("*.mov", "*.webm") for p in Path(project_dir).glob(ext)
    )
    if not matches:
        raise FileNotFoundError(f"No .mov or .webm file found in {project_dir}")
    if len(matches) > 1:
        print(f"Warning: multiple recordings found, using {matches[0].name}")
    return str(matches[0])


def main():
    original_path = find_source_video(config.PROJECT_DIR)
    print(f"Source: {original_path}")

    speed = config.SOURCE_SPEED_MULTIPLIER
    if speed != 1.0:
        sped_up_path = config.SPED_UP_VIDEO
        if os.path.exists(sped_up_path):
            print(f"Sped-up video already exists, skipping: {Path(sped_up_path).name}")
        else:
            print(f"Creating {speed}x speed version...")
            create_sped_up_video(original_path, sped_up_path, speed)
            print(f"  Saved: {Path(sped_up_path).name}")
        video_path = sped_up_path
    else:
        video_path = original_path

    print(f"Extracting 1 frame every {config.FRAME_INTERVAL_SECONDS}s...")
    raw_count = extract_raw_frames(video_path, config.RAW_FRAMES_DIR, config.FRAME_INTERVAL_SECONDS)
    print(f"  {raw_count} raw frames extracted")

    print(f"Deduplicating (threshold={config.SIMILARITY_THRESHOLD})...")
    kept = dedup_frames(config.RAW_FRAMES_DIR, config.FRAMES_DIR, config.SIMILARITY_THRESHOLD)
    print(f"  Kept {kept} / {raw_count} frames ({raw_count - kept} idle frames removed)")
    print(f"  Output: {config.FRAMES_DIR}/")


if __name__ == "__main__":
    main()
