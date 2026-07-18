import json
import os
import glob
import base64
import time
import io
import anthropic
from PIL import Image
import config


def load_captions(path: str) -> list:
    """Load captions.json, returning [] if missing or empty."""
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def save_captions(path: str, captions: list) -> None:
    with open(path, "w") as f:
        json.dump(captions, f, indent=2)


def get_captioned_frames(captions: list) -> set:
    return {entry["frame"] for entry in captions}


def resize_for_vision(image_path: str, max_width: int = 1280) -> bytes:
    """Return PNG bytes resized to max_width, preserving aspect ratio."""
    img = Image.open(image_path).convert("RGB")
    if img.width > max_width:
        ratio = max_width / img.width
        new_size = (max_width, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def caption_frame(
    image_path: str,
    client: anthropic.Anthropic,
    model: str,
    prompt: str,
    retries: int = 1,
    backoff: float = 2.0,
) -> str:
    """Send a frame to Claude Vision and return the caption string.
    Returns 'ERROR: <msg>' if all retries fail."""
    image_bytes = resize_for_vision(image_path)
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    for attempt in range(retries + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            return response.content[0].text.strip()
        except Exception as e:
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
            else:
                return f"ERROR: {e}"


def make_anthropic_client() -> anthropic.Anthropic:
    if config.AI_GATEWAY_API_KEY:
        return anthropic.Anthropic(
            api_key=config.AI_GATEWAY_API_KEY,
            base_url="https://ai-gateway.vercel.sh",
        )
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def main():
    client = make_anthropic_client()
    frame_paths = sorted(glob.glob(os.path.join(config.FRAMES_DIR, "*.png")))

    if not frame_paths:
        print(f"No frames found in {config.FRAMES_DIR}. Run 01_extract_frames.py first.")
        return

    captions = load_captions(config.CAPTIONS_FILE)
    already_done = get_captioned_frames(captions)

    todo = [f for f in frame_paths if f not in already_done]
    print(f"{len(already_done)} already captioned, {len(todo)} remaining.")

    for i, frame_path in enumerate(todo, start=1):
        caption = caption_frame(
            frame_path, client, config.CLAUDE_MODEL, config.CAPTION_PROMPT
        )
        relative_path = os.path.relpath(frame_path, config.PROJECT_DIR)
        captions.append({"frame": relative_path, "caption": caption})
        save_captions(config.CAPTIONS_FILE, captions)
        print(f"  [{i}/{len(todo)}] {os.path.basename(frame_path)}: {caption[:60]}...")

    print(f"Done. captions.json has {len(captions)} entries.")


if __name__ == "__main__":
    main()
