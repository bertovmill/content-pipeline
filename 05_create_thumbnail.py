from __future__ import annotations
import json
from pathlib import Path
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import anthropic
import config

KNOWN_DOMAINS = {
    # AI / LLM
    "anthropic": "anthropic.com",
    "openai": "openai.com",
    "huggingface": "huggingface.co",
    "mistral": "mistral.ai",
    "cohere": "cohere.com",
    "groq": "groq.com",
    "together": "together.ai",
    "replicate": "replicate.com",
    "openrouter": "openrouter.ai",
    # Dev tools
    "github": "github.com",
    "gitlab": "gitlab.com",
    "cursor": "cursor.sh",
    "vscode": "code.visualstudio.com",
    "vs code": "code.visualstudio.com",
    "vercel": "vercel.com",
    "supabase": "supabase.com",
    "planetscale": "planetscale.com",
    "neon": "neon.tech",
    "railway": "railway.app",
    "render": "render.com",
    "netlify": "netlify.com",
    # Data / infra
    "langchain": "langchain.com",
    "langsmith": "smith.langchain.com",
    "langgraph": "langchain.com",
    "pinecone": "pinecone.io",
    "weaviate": "weaviate.io",
    "chroma": "trychroma.com",
    # Common
    "google": "google.com",
    "notion": "notion.so",
    "linear": "linear.app",
    "figma": "figma.com",
    "stripe": "stripe.com",
    "twilio": "twilio.com",
    "aws": "aws.amazon.com",
    "python": "python.org",
    "npm": "npmjs.com",
    "node.js": "nodejs.org",
    "nodejs": "nodejs.org",
    "nextjs": "nextjs.org",
    "next.js": "nextjs.org",
    "typescript": "typescriptlang.org",
    "docker": "docker.com",
}

THUMBNAIL_SIZE = (1280, 720)
BG_COLOR = (15, 15, 30)
TEXT_COLOR = (255, 255, 255)
ACCENT_COLOR = (100, 180, 255)


def company_to_domain(name: str) -> str:
    """Map a company/tool name to its primary domain for Clearbit logo lookup."""
    key = name.lower().strip()
    if key in KNOWN_DOMAINS:
        return KNOWN_DOMAINS[key]
    key_nospace = key.replace(" ", "")
    if key_nospace in KNOWN_DOMAINS:
        return KNOWN_DOMAINS[key_nospace]
    return f"{key_nospace}.com"


def fetch_logo(domain: str, size: int = 128) -> Image.Image | None:
    """Fetch a company logo via Google's favicon service. Returns PIL Image or None."""
    url = f"https://www.google.com/s2/favicons?sz={size}&domain={domain}"
    try:
        resp = requests.get(url, timeout=5, allow_redirects=True)
        if resp.status_code == 200 and resp.content:
            img = Image.open(BytesIO(resp.content)).convert("RGBA")
            # Google returns a 16x16 grey fallback for unknown domains — skip it
            if img.size[0] < 32:
                return None
            return img
    except Exception:
        pass
    return None


def extract_companies(captions: list, client: anthropic.Anthropic, model: str) -> list:
    """Ask Claude to extract company/tool names from captions. Returns list of strings."""
    caption_text = "\n".join(
        entry["caption"] for entry in captions
        if not entry["caption"].startswith("ERROR:")
    )
    prompt = (
        "From the following tutorial captions, extract the names of all software tools, "
        "libraries, and companies mentioned. Return a JSON array of strings only, no explanation.\n\n"
        f"{caption_text}"
    )
    response = client.messages.create(
        model=model,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(raw)


def read_title() -> str:
    """Thumbnail title: prefer the line under a '## Thumbnail Title' heading in
    youtube.md (short, punchy), else fall back to the main '# ' title."""
    youtube_file = Path(config.YOUTUBE_FILE)
    if youtube_file.exists():
        lines = youtube_file.read_text().splitlines()
        for i, line in enumerate(lines):
            if line.strip().lower() == "## thumbnail title":
                for nxt in lines[i + 1:]:
                    if nxt.strip():
                        return nxt.strip()
        for line in lines:
            line = line.strip()
            if line.startswith("# "):
                return line[2:]
    return "Tutorial"


def load_bold_font(size: int):
    """Load a bold font, trying common macOS bold faces before falling back."""
    candidates = [
        ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
        ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
        ("/System/Library/Fonts/Helvetica.ttc", 1),
        ("/Library/Fonts/Arial Bold.ttf", 0),
    ]
    for path, index in candidates:
        try:
            return ImageFont.truetype(path, size, index=index)
        except Exception:
            continue
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except Exception:
        return ImageFont.load_default()


def make_circular(img: Image.Image, size: int) -> Image.Image:
    """Resize image to size x size and apply a circular mask."""
    img = img.resize((size, size), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([(0, 0), (size, size)], fill=255)
    img.putalpha(mask)
    return img


def load_headshot(path: str, size: int = 420) -> Image.Image | None:
    """Load the headshot PNG, make it circular, return RGBA image or None."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        return make_circular(Image.open(p), size)
    except Exception:
        return None


def compose_thumbnail(title: str, logos: list, output_path: str, headshot: Image.Image | None = None) -> None:
    """Compose a 1280x720 thumbnail with title, logos, and optional headshot using Pillow."""
    img = Image.new("RGB", THUMBNAIL_SIZE, BG_COLOR)
    draw = ImageDraw.Draw(img)

    font_large = load_bold_font(72)  # bold title
    try:
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
    except Exception:
        font_small = ImageFont.load_default()

    draw.rectangle([(0, 0), (1280, 8)], fill=ACCENT_COLOR)

    # Paste headshot on right side before drawing text
    headshot_x = 0
    text_max_width = 1180
    if headshot is not None:
        hs_size = headshot.size[0]
        headshot_x = 1280 - hs_size - 30
        headshot_y = (720 - hs_size) // 2
        # Subtle glow ring behind headshot
        glow = Image.new("RGBA", (hs_size + 20, hs_size + 20), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse([(0, 0), (hs_size + 20, hs_size + 20)], fill=(*ACCENT_COLOR, 60))
        img.paste(glow, (headshot_x - 10, headshot_y - 10), glow)
        img.paste(headshot, (headshot_x, headshot_y), headshot)
        text_max_width = headshot_x - 60  # keep title text in the left zone

    words = title.split()
    lines = []
    current = []
    for word in words:
        current.append(word)
        test_line = " ".join(current)
        bbox = draw.textbbox((0, 0), test_line, font=font_large)
        if bbox[2] > text_max_width:
            current.pop()
            lines.append(" ".join(current))
            current = [word]
    lines.append(" ".join(current))

    y = 80
    for line in lines[:3]:
        # stroke_width thickens the glyphs so the title reads bold even if the
        # bold face is unavailable
        draw.text((50, y), line, font=font_large, fill=TEXT_COLOR,
                  stroke_width=1, stroke_fill=TEXT_COLOR)
        y += 90

    logo_y = 480
    logo_x = 50
    logo_size = 80
    for logo_img in logos[:6]:
        logo_resized = logo_img.resize((logo_size, logo_size), Image.LANCZOS)
        if logo_resized.mode == "RGBA":
            img.paste(logo_resized, (logo_x, logo_y), logo_resized)
        else:
            img.paste(logo_resized, (logo_x, logo_y))
        logo_x += logo_size + 20

    draw.text((50, 620), "Tutorial", font=font_small, fill=ACCENT_COLOR)

    img.save(output_path, "PNG")


def main():
    client = anthropic.Anthropic(
        api_key=config.AI_GATEWAY_API_KEY or config.ANTHROPIC_API_KEY,
        **({"base_url": "https://ai-gateway.vercel.sh"} if config.AI_GATEWAY_API_KEY else {}),
    )

    with open(config.CAPTIONS_FILE, "r") as f:
        captions = json.load(f)

    print("Extracting company names from captions...")
    companies = extract_companies(captions, client, config.CLAUDE_MODEL)
    print(f"  Found: {companies}")

    logos = []
    for company in companies:
        domain = company_to_domain(company)
        logo = fetch_logo(domain)
        if logo:
            logos.append(logo)
            print(f"  Logo fetched: {company} ({domain})")
        else:
            print(f"  No logo: {company} ({domain})")

    headshot = load_headshot(config.HEADSHOT_FILE)
    if headshot:
        print("Headshot loaded.")
    else:
        print(f"No headshot found at {config.HEADSHOT_FILE}, skipping.")

    title = read_title()
    print(f"Composing thumbnail: '{title}'...")
    compose_thumbnail(title, logos, config.THUMBNAIL_FILE, headshot=headshot)
    print(f"Done. Thumbnail: {config.THUMBNAIL_FILE}")


if __name__ == "__main__":
    main()
