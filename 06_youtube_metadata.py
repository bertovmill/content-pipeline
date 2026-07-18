import json
import anthropic
import config


def generate_metadata(captions: list, client: anthropic.Anthropic, model: str) -> dict:
    """Ask Claude to generate YouTube title, description, and tags from captions."""
    caption_text = "\n".join(
        f"[{i}] {e['caption']}"
        for i, e in enumerate(captions)
        if not e["caption"].startswith("ERROR:")
    )
    prompt = (
        "You are writing YouTube metadata for a screen-recording tutorial video.\n"
        "Based on these frame captions, generate:\n"
        "1. A concise, keyword-rich YouTube title (under 70 chars)\n"
        "2. A short, punchy thumbnail title (3-6 words, no parentheticals) for the video thumbnail\n"
        "3. A description (150-300 words) explaining what viewers will learn\n"
        "4. A list of 10-15 relevant tags\n\n"
        "Do NOT use em dashes (—) anywhere. Use commas, periods, or parentheses instead.\n"
        "Return ONLY a JSON object with keys: title, thumbnail_title, description, tags (array of strings).\n\n"
        f"Captions:\n{caption_text}"
    )
    response = client.messages.create(
        model=model,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(raw)


def write_youtube_file(metadata: dict, output_path: str) -> None:
    lines = [f"# {metadata['title']}", ""]
    # Optional short title for the thumbnail (Stage 5 reads this if present)
    thumb = metadata.get("thumbnail_title")
    if thumb:
        lines += ["## Thumbnail Title", thumb, ""]
    lines += [
        "## Description",
        "",
        metadata["description"],
        "",
        "## Tags",
        "",
        ", ".join(metadata["tags"]),
    ]
    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    client = anthropic.Anthropic(
        api_key=config.AI_GATEWAY_API_KEY or config.ANTHROPIC_API_KEY,
        **({"base_url": "https://ai-gateway.vercel.sh"} if config.AI_GATEWAY_API_KEY else {}),
    )

    with open(config.CAPTIONS_FILE, "r") as f:
        captions = json.load(f)

    print("Generating YouTube metadata...")
    metadata = generate_metadata(captions, client, config.CLAUDE_MODEL)

    write_youtube_file(metadata, config.YOUTUBE_FILE)
    print(f"Done. {config.YOUTUBE_FILE}")
    print(f"\nTitle: {metadata['title']}")
    print(f"Tags: {', '.join(metadata['tags'])}")


if __name__ == "__main__":
    main()
