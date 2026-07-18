import json
import os
import anthropic
import config


def generate_article(captions: list, title: str, client: anthropic.Anthropic, model: str) -> str:
    """Ask Claude to write a full tutorial article from frame captions, embedding screenshots."""
    caption_block = "\n".join(
        f"[Frame {i+1} — screenshot: frames/{os.path.basename(e['frame'])}]\n{e['caption']}"
        for i, e in enumerate(captions)
        if not e["caption"].startswith("ERROR:")
    )

    prompt = (
        f"You are writing a technical tutorial article titled: \"{title}\"\n\n"
        "Based on the following narrated frames from a screen-recording tutorial, "
        "write a complete, well-structured blog post. The article should:\n"
        "- Open with a short intro explaining what the reader will learn and why it matters\n"
        "- Group related frames into logical sections with ## headings\n"
        "- Embed each screenshot using Markdown: ![description](frames/XXXX.png), "
        "placing each image directly after the paragraph that references it\n"
        "- Use second person ('you'), present tense, friendly and clear tone\n"
        "- End with a short summary and next steps\n"
        "- Include inline code formatting for commands, file names, and code snippets\n"
        "- Do NOT use em dashes (—) anywhere. Use commas, periods, or parentheses instead\n\n"
        "Frame narrations:\n"
        f"{caption_block}"
    )

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def main():
    client = anthropic.Anthropic(
        api_key=config.AI_GATEWAY_API_KEY or config.ANTHROPIC_API_KEY,
        **({"base_url": "https://ai-gateway.vercel.sh"} if config.AI_GATEWAY_API_KEY else {}),
    )

    with open(config.CAPTIONS_FILE, "r") as f:
        captions = json.load(f)

    # Pull title from youtube.md if it exists, else use a fallback
    title = "Tutorial"
    if os.path.exists(config.YOUTUBE_FILE):
        with open(config.YOUTUBE_FILE, "r") as f:
            first_line = f.readline().strip()
            if first_line.startswith("# "):
                title = first_line[2:]

    LINKEDIN_NOTE = (
        "> Thanks for visiting this article! If you would like to connect with me personally, "
        "please connect with me on LinkedIn here: https://www.linkedin.com/in/bertomill/\n"
    )

    print(f"Generating article: \"{title}\"...")
    article = generate_article(captions, title, client, config.CLAUDE_MODEL)

    # Insert LinkedIn note after the first heading (title line)
    lines = article.split("\n")
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("# "):
            insert_at = i + 1
            break
    lines.insert(insert_at, "\n" + LINKEDIN_NOTE)
    article = "\n".join(lines)

    with open(config.ARTICLE_FILE, "w") as f:
        f.write(article)

    word_count = len(article.split())
    print(f"Done. {config.ARTICLE_FILE} ({word_count} words)")


if __name__ == "__main__":
    main()
