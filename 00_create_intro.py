"""
Stage 0: Create intro screens and prepend to output.mp4.

Produces three screens concatenated before the main video:
  1. Branded card  — headshot, name, LinkedIn QR. AI narrates a welcome + overview.
  2. Title screen  — video title + date. AI reads the title.
  3. TOC screen    — numbered list of topics. AI reads the chapter list.

Clip durations are driven by TTS length, not hardcoded.
Run after Stage 6 (needs youtube.md) and Stage 2 (needs captions.json).
Final output: output_with_intro.mp4
"""

import json
import os
import subprocess
from datetime import date
from pathlib import Path

import anthropic
import qrcode
from elevenlabs import ElevenLabs
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_DIR = Path(config.PROJECT_DIR)
HEADSHOT_PATH = PROJECT_DIR / "berto-mill.png"
OUTPUT_VIDEO = PROJECT_DIR / "output.mp4"
FINAL_OUTPUT = PROJECT_DIR / "output_with_intro.mp4"

LINKEDIN_URL = "https://www.linkedin.com/in/bertomill/"
CREATOR_NAME = "Berto Mill"

VIDEO_W, VIDEO_H = 3456, 2234
FADE = 0.5

BG_DARK   = "#0d0d1a"
ACCENT    = "#4f46e5"
WHITE     = "#ffffff"
SUBTEXT   = "#9b9bc0"
HIGHLIGHT = "#818cf8"

FONT_SF = "/System/Library/Fonts/SFNS.ttf"
FONT_HV = "/System/Library/Fonts/Helvetica.ttc"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in [FONT_SF, FONT_HV]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap(text: str, draw: ImageDraw.Draw, font, max_width: int) -> list[str]:
    words = text.split()
    lines, current = [], []
    for word in words:
        current.append(word)
        if draw.textbbox((0, 0), " ".join(current), font=font)[2] > max_width:
            current.pop()
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def _gradient_bg(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h), BG_DARK)
    draw = ImageDraw.Draw(img)
    for i in range(h):
        t = i / h
        draw.line([(0, i), (w, i)], fill=(
            int(13 + t * 8), int(13 + t * 5), int(26 + t * 20)
        ))
    return img


def _get_duration(path: str) -> float:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ], capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def _make_still_clip(frame_path: str, duration: float, output_path: str) -> None:
    fade_start = max(0, duration - FADE)
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", frame_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "28",
        "-t", str(duration), "-pix_fmt", "yuv420p", "-r", "25",
        "-vf", f"fade=t=in:st=0:d={FADE},fade=t=out:st={fade_start}:d={FADE}",
        output_path,
    ], check=True, capture_output=True)


def _make_clip_with_tts(frame_path: str, tts_path: str, output_path: str) -> None:
    """Combine a still frame with a TTS audio file into a single clip."""
    duration = _get_duration(tts_path)
    video_only = output_path.replace(".mp4", "_vonly.mp4")
    _make_still_clip(frame_path, duration, video_only)
    subprocess.run([
        "ffmpeg", "-y", "-i", video_only, "-i", tts_path,
        "-c:v", "copy", "-c:a", "aac", "-shortest",
        output_path,
    ], check=True, capture_output=True)
    Path(video_only).unlink(missing_ok=True)


def _add_silent_audio(video_path: str) -> str:
    """Fallback: attach silence if no TTS available."""
    # Check if video already has audio stream
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path,
    ], capture_output=True, text=True)
    if probe.stdout.strip():
        return video_path  # already has audio
    out = video_path.replace(".mp4", "_audio.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-c:v", "copy", "-c:a", "aac", "-shortest", out,
    ], check=True, capture_output=True)
    return out


# ---------------------------------------------------------------------------
# TTS generation
# ---------------------------------------------------------------------------

def generate_tts(text: str, output_path: str) -> float:
    """Generate ElevenLabs TTS, save to output_path, return duration in seconds."""
    client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
    audio_chunks = client.text_to_speech.convert(
        voice_id=config.ELEVENLABS_VOICE_ID,
        text=text,
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
    )
    with open(output_path, "wb") as f:
        for chunk in audio_chunks:
            f.write(chunk)
    return _get_duration(output_path)


# ---------------------------------------------------------------------------
# Frame builders
# ---------------------------------------------------------------------------

def build_branded_frame() -> str:
    """Headshot + name + LinkedIn QR card."""
    img = _gradient_bg(VIDEO_W, VIDEO_H)
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (18, VIDEO_H)], fill=ACCENT)

    PAD, PHOTO_SIZE, QR_SIZE = 160, 960, 600
    cx = VIDEO_H // 2
    photo_x, photo_y = PAD + 18, cx - PHOTO_SIZE // 2
    text_x = photo_x + PHOTO_SIZE + 120

    if HEADSHOT_PATH.exists():
        raw = Image.open(HEADSHOT_PATH)
        w, h = raw.size
        side = min(w, h)
        raw = raw.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
        raw = raw.resize((PHOTO_SIZE, PHOTO_SIZE), Image.LANCZOS).convert("RGBA")
        mask = Image.new("L", (PHOTO_SIZE, PHOTO_SIZE), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, PHOTO_SIZE, PHOTO_SIZE), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(2))
        hs = Image.new("RGBA", (PHOTO_SIZE, PHOTO_SIZE), (0, 0, 0, 0))
        hs.paste(raw, mask=mask)
        rs = PHOTO_SIZE + 32
        ring = Image.new("RGBA", (rs, rs), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse((0, 0, rs - 1, rs - 1), outline=ACCENT, width=12)
        ring = ring.filter(ImageFilter.GaussianBlur(8))
        img.paste(ring, (photo_x - 16, photo_y - 16), ring)
        img.paste(hs, (photo_x, photo_y), hs)
        draw = ImageDraw.Draw(img)

    f_label = _font(100)
    f_name  = _font(220)
    f_tag   = _font(80)
    f_url   = _font(78)

    label_y = cx - 280
    name_y  = label_y + 120
    tag_y   = name_y + 250
    url_y   = tag_y + 110

    draw.line([(text_x - 60, label_y), (text_x - 60, tag_y + 80)], fill=ACCENT, width=6)
    draw.text((text_x, label_y), "Created by", font=f_label, fill=SUBTEXT)
    draw.text((text_x, name_y),  CREATOR_NAME, font=f_name,  fill=WHITE)
    draw.text((text_x, tag_y),   "Software Developer & Content Creator", font=f_tag, fill=SUBTEXT)

    url_text = "linkedin.com/in/bertomill"
    bb = draw.textbbox((0, 0), url_text, font=f_url)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    draw.rounded_rectangle([text_x - 40, url_y - 20, text_x + tw + 40, url_y + th + 20],
                           radius=30, fill="#1d1d3a")
    draw.text((text_x, url_y), url_text, font=f_url, fill=HIGHLIGHT)

    qr_x = VIDEO_W - PAD - QR_SIZE
    qr_y = VIDEO_H - PAD - QR_SIZE
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
    qr.add_data(LINKEDIN_URL)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#1a1a2e", back_color="white").convert("RGB")
    qr_img = qr_img.resize((QR_SIZE, QR_SIZE), Image.LANCZOS)
    draw.rounded_rectangle([qr_x - 30, qr_y - 120, qr_x + QR_SIZE + 30, qr_y + QR_SIZE + 30],
                           radius=30, fill="#ffffff")
    img.paste(qr_img, (qr_x, qr_y))
    draw.text((qr_x + QR_SIZE // 2, qr_y - 70), "Scan to connect",
              font=f_url, fill="#1a1a2e", anchor="mm")

    out = str(PROJECT_DIR / "tmp_intro_branded.png")
    img.save(out, "PNG")
    return out


def build_title_frame(title: str) -> str:
    """Large centered title + date."""
    img = _gradient_bg(VIDEO_W, VIDEO_H)
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (VIDEO_W, 16)], fill=ACCENT)
    draw.rectangle([(0, VIDEO_H - 16), (VIDEO_W, VIDEO_H)], fill=ACCENT)

    f_title = _font(190)
    f_sub   = _font(95)
    f_date  = _font(72)

    margin = 200
    lines = _wrap(title, draw, f_title, VIDEO_W - margin * 2)
    line_h = 230
    block_h = len(lines) * line_h
    y = (VIDEO_H - block_h) // 2 - 120

    for line in lines:
        draw.text((margin, y), line, font=f_title, fill=WHITE)
        y += line_h

    y += 70
    draw.text((margin, y), "Tutorial", font=f_sub, fill=HIGHLIGHT)
    y += 120
    draw.text((margin, y), date.today().strftime("%B %d, %Y"), font=f_date, fill=SUBTEXT)

    out = str(PROJECT_DIR / "tmp_intro_title.png")
    img.save(out, "PNG")
    return out


def build_toc_frame(title: str, topics: list[str]) -> str:
    """Numbered table of contents."""
    img = _gradient_bg(VIDEO_W, VIDEO_H)
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (VIDEO_W, 16)], fill=ACCENT)
    draw.rectangle([(0, VIDEO_H - 16), (VIDEO_W, VIDEO_H)], fill=ACCENT)

    f_header = _font(130)
    f_sub    = _font(75)
    f_item   = _font(88)

    margin = 180
    y = 130

    draw.text((margin, y), "What We'll Cover", font=f_header, fill=WHITE)
    y += 160
    subtitle = title if len(title) <= 70 else title[:67] + "..."
    draw.text((margin, y), subtitle, font=f_sub, fill=SUBTEXT)
    y += 120
    draw.rectangle([(margin, y), (VIDEO_W - margin, y + 5)], fill=ACCENT)
    y += 65

    for i, topic in enumerate(topics, start=1):
        num = f"{i}."
        num_w = draw.textbbox((0, 0), num, font=f_item)[2]
        draw.text((margin, y), num, font=f_item, fill=ACCENT)
        draw.text((margin + num_w + 35, y), topic, font=f_item, fill=WHITE)
        y += 130
        if y > VIDEO_H - 220:
            break

    out = str(PROJECT_DIR / "tmp_intro_toc.png")
    img.save(out, "PNG")
    return out


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def read_title() -> str:
    if Path(config.YOUTUBE_FILE).exists():
        with open(config.YOUTUBE_FILE) as f:
            line = f.readline().strip()
            if line.startswith("# "):
                return line[2:]
    return "Tutorial"


def extract_toc_topics(n: int = 8) -> list[str]:
    """Use Claude to extract accurate chapter topics from captions."""
    with open(config.CAPTIONS_FILE) as f:
        captions = json.load(f)
    valid = [e for e in captions if not e["caption"].startswith("ERROR:")]
    sample = valid[:60]
    captions_text = "\n".join(f"{i+1}. {e['caption']}" for i, e in enumerate(sample))

    api_key = config.AI_GATEWAY_API_KEY or config.ANTHROPIC_API_KEY
    kwargs = {"api_key": api_key}
    if config.AI_GATEWAY_API_KEY:
        kwargs["base_url"] = "https://ai-gateway.vercel.sh"
    client = anthropic.Anthropic(**kwargs)

    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": (
                f"Based on these tutorial captions, generate exactly {n} short chapter titles "
                f"(2-5 words each) that accurately describe what's covered in this specific video. "
                f"Return only a JSON array of strings, nothing else.\n\nCaptions:\n{captions_text}"
            ),
        }]
    )
    raw = response.content[0].text.strip()
    # Strip markdown code fences if the model wrapped the JSON
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        topics = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extract the first [...] array from the text
        start, end = raw.find("["), raw.rfind("]")
        if start != -1 and end != -1:
            topics = json.loads(raw[start:end + 1])
        else:
            raise
    return topics[:n]


def generate_branded_voiceover(title: str, topics: list[str]) -> str:
    """Use Claude to write a short welcome script for the branded card."""
    api_key = config.AI_GATEWAY_API_KEY or config.ANTHROPIC_API_KEY
    kwargs = {"api_key": api_key}
    if config.AI_GATEWAY_API_KEY:
        kwargs["base_url"] = "https://ai-gateway.vercel.sh"
    client = anthropic.Anthropic(**kwargs)

    topics_str = ", ".join(topics[:4])
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=150,
        messages=[{
            "role": "user",
            "content": (
                f"Write a short 2-3 sentence spoken welcome for a YouTube tutorial called '{title}'. "
                f"The video covers: {topics_str}. "
                f"Sound friendly and energetic. Start with 'Hey everyone, welcome back!' "
                f"End with 'Let's get into it.' Return only the script text, no quotes or labels."
            ),
        }]
    )
    return response.content[0].text.strip()


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def concat_clips(clips: list[str], main_video: str, output: str) -> None:
    """Concatenate intro clips (must already have audio) + main video."""
    # Ensure all clips have audio tracks
    ready_clips = [_add_silent_audio(c) for c in clips]
    all_inputs = ready_clips + [main_video]
    n = len(all_inputs)

    # The concat filter requires every input to share the same resolution, SAR
    # and frame rate. Intro clips are rendered at the recording's native size /
    # fps, which differ from the composed main video, so normalize all inputs to
    # the main video's resolution (scale-to-fit + pad, no distortion) and a
    # common fps before concatenating.
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", main_video],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    tw, th = (int(x) for x in probe.split("x"))
    fps = 30

    inputs = []
    for path in all_inputs:
        inputs.extend(["-i", path])

    norm = "".join(
        f"[{i}:v]scale={tw}:{th}:force_original_aspect_ratio=decrease,"
        f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v{i}];"
        for i in range(n)
    )
    concat_srcs = "".join(f"[v{i}][{i}:a]" for i in range(n))
    filter_complex = f"{norm}{concat_srcs}concat=n={n}:v=1:a=1[outv][outa]"

    subprocess.run([
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac",
        output,
    ], check=True, capture_output=True)

    for c in ready_clips:
        if c not in clips:
            Path(c).unlink(missing_ok=True)


def cleanup_tmp() -> None:
    for name in [
        "tmp_intro_branded.png", "tmp_intro_title.png", "tmp_intro_toc.png",
        "tmp_clip_branded.mp4", "tmp_clip_title.mp4", "tmp_clip_toc.mp4",
        "tmp_tts_branded.mp3", "tmp_tts_title.mp3", "tmp_tts_toc.mp3",
    ]:
        (PROJECT_DIR / name).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== Stage 0: Creating intro screens ===\n")

    title  = read_title()
    print(f"Title: {title}")

    print("Extracting TOC topics with Claude...")
    topics = extract_toc_topics()
    print(f"Topics: {topics}\n")

    # Generate voiceover scripts
    print("Generating voiceover scripts...")
    branded_script = generate_branded_voiceover(title, topics)
    title_script   = title
    toc_script     = "In this tutorial, we'll cover: " + ". ".join(topics) + ". Let's go!"
    print(f"  Branded: {branded_script[:60]}...")

    # Generate TTS audio (clips duration will match TTS length)
    print("Generating TTS voiceovers...")
    branded_tts = str(PROJECT_DIR / "tmp_tts_branded.mp3")
    title_tts   = str(PROJECT_DIR / "tmp_tts_title.mp3")
    toc_tts     = str(PROJECT_DIR / "tmp_tts_toc.mp3")

    generate_tts(branded_script, branded_tts)
    generate_tts(title_script,   title_tts)
    generate_tts(toc_script,     toc_tts)

    # Build frames
    print("Building frames...")
    branded_png = build_branded_frame()
    title_png   = build_title_frame(title)
    toc_png     = build_toc_frame(title, topics)

    # Build clips with TTS audio baked in
    print("Rendering clips with voiceover...")
    branded_clip = str(PROJECT_DIR / "tmp_clip_branded.mp4")
    title_clip   = str(PROJECT_DIR / "tmp_clip_title.mp4")
    toc_clip     = str(PROJECT_DIR / "tmp_clip_toc.mp4")

    _make_clip_with_tts(branded_png, branded_tts, branded_clip)
    _make_clip_with_tts(title_png,   title_tts,   title_clip)
    _make_clip_with_tts(toc_png,     toc_tts,     toc_clip)

    # Concatenate
    print("Assembling final video...")
    concat_clips(
        [branded_clip, title_clip, toc_clip],
        str(OUTPUT_VIDEO),
        str(FINAL_OUTPUT),
    )

    cleanup_tmp()
    print(f"\nDone. {FINAL_OUTPUT}")


if __name__ == "__main__":
    main()
