"""Ideation stage (pre-production): find the most trending AI tool to make a video about.

Runs BEFORE you record. Fully self-contained, all sources are free and keyless:

  1. MOMENTUM  — Hacker News (recency+points), GitHub Trending (stars-this-week velocity),
                 Reddit hot (best-effort; Reddit blocks server IPs without OAuth).
  2. Claude distills the raw signals into a deduped list of candidate tools.
  3. DEMAND    — Google autocomplete/suggest per candidate. Google only suggests phrases
                 people actually search, so on-topic suggestions = real search demand
                 (and reveal namespace collisions, e.g. "strix" -> "strixhaven" MTG).
  4. Claude ranks by DEMAND x MOMENTUM and writes content-ideas.md + candidates.json.

Optional upgrade: if you get an Ahrefs API plan with Keywords Explorer access, you can
layer exact search volume on top via the Ahrefs MCP in-session (this account's plan
returns "Insufficient plan", so we use Google autocomplete as the free demand proxy).

Usage:
    python3 ideate.py            # skips if content-ideas.md already exists
    python3 ideate.py --refresh  # re-pull everything
"""

import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import anthropic
import requests

import config

USER_AGENT = "content-pipeline-ideation/1.0 (github.com/bertomill)"
# Reddit and some CDNs reject non-browser UAs; use a realistic one for those.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
AI_TERMS = ["ai", "llm", "agent", "gpt", "claude", "model", "rag", "mcp", "coding"]


def _get_json(url: str, params: dict | None = None) -> dict | list:
    resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_hacker_news() -> list[dict]:
    """Recent HN stories above a points threshold, from the last N hours."""
    since = int((datetime.now(timezone.utc) - timedelta(hours=config.IDEATION_HN_LOOKBACK_HOURS)).timestamp())
    try:
        data = _get_json(
            "https://hn.algolia.com/api/v1/search_by_date",
            {
                "tags": "story",
                "numericFilters": f"created_at_i>{since},points>{config.IDEATION_HN_MIN_POINTS}",
                "hitsPerPage": 60,
            },
        )
    except Exception as e:
        print(f"  ! Hacker News fetch failed: {e}")
        return []
    items = []
    for hit in data.get("hits", []):
        title = hit.get("title") or ""
        if not title:
            continue
        items.append({
            "source": "hackernews",
            "title": title,
            "engagement": hit.get("points", 0),
            "comments": hit.get("num_comments", 0),
            "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
        })
    print(f"  Hacker News: {len(items)} recent stories")
    return items


def _github_trending_scrape() -> list[dict]:
    """Scrape the public Trending page for stars-gained-this-week velocity (no auth)."""
    resp = requests.get(
        "https://github.com/trending",
        params={"since": "weekly"},
        headers={"User-Agent": BROWSER_UA},
        timeout=20,
    )
    resp.raise_for_status()
    items = []
    # Each repo lives in an <article class="Box-row"> block.
    for block in resp.text.split('class="Box-row"')[1:]:
        href = re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', block)
        if not href:
            continue
        full_name = re.sub(r"\s+", "", href.group(1))
        desc = re.search(r'<p[^>]*class="col-9[^"]*"[^>]*>(.*?)</p>', block, re.DOTALL)
        desc_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", desc.group(1))).strip() if desc else ""
        stars_wk = re.search(r"([\d,]+)\s+stars\s+this\s+week", block)
        velocity = int(stars_wk.group(1).replace(",", "")) if stars_wk else 0
        items.append({
            "source": "github",
            "title": f"{full_name} — {desc_text}".strip(" —"),
            "engagement": velocity,          # stars gained this week = real momentum
            "comments": 0,
            "url": f"https://github.com/{full_name}",
        })
    return items


def _github_search_new() -> list[dict]:
    """Authenticated fallback: newest AI repos sorted by total stars (needs a token)."""
    since = (datetime.now(timezone.utc) - timedelta(days=config.IDEATION_GITHUB_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    resp = requests.get(
        "https://api.github.com/search/repositories",
        params={"q": f"created:>{since} ({' OR '.join(AI_TERMS)})", "sort": "stars", "order": "desc", "per_page": 30},
        headers={"User-Agent": USER_AGENT, "Authorization": f"Bearer {config.IDEATION_GITHUB_TOKEN}"},
        timeout=20,
    )
    resp.raise_for_status()
    return [{
        "source": "github",
        "title": f"{r['full_name']} — {r.get('description') or ''}".strip(" —"),
        "engagement": r.get("stargazers_count", 0),
        "comments": r.get("open_issues_count", 0),
        "url": r.get("html_url", ""),
    } for r in resp.json().get("items", [])]


def fetch_github() -> list[dict]:
    """Prefer authenticated new-repo search if a token is set; else scrape Trending velocity."""
    try:
        items = _github_search_new() if config.IDEATION_GITHUB_TOKEN else _github_trending_scrape()
    except Exception as e:
        print(f"  ! GitHub fetch failed: {e}")
        return []
    label = "new AI repos (search)" if config.IDEATION_GITHUB_TOKEN else "trending repos (weekly velocity)"
    print(f"  GitHub: {len(items)} {label}")
    return items


def fetch_reddit() -> list[dict]:
    """Hot posts across the configured AI subreddits."""
    items = []
    for sub in config.IDEATION_SUBREDDITS:
        try:
            resp = requests.get(
                f"https://www.reddit.com/r/{sub}/hot.json",
                params={"limit": 15},
                headers={"User-Agent": BROWSER_UA},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  ! Reddit r/{sub} fetch failed: {e}")
            continue
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            if post.get("stickied"):
                continue
            items.append({
                "source": f"reddit/{sub}",
                "title": post.get("title", ""),
                "engagement": post.get("ups", 0),
                "comments": post.get("num_comments", 0),
                "url": f"https://www.reddit.com{post.get('permalink', '')}",
            })
        time.sleep(1)  # be polite to Reddit
    print(f"  Reddit: {len(items)} hot posts across {len(config.IDEATION_SUBREDDITS)} subs")
    return items


def distill_candidates(signals: list[dict], client: anthropic.Anthropic, model: str) -> list[dict]:
    """Ask Claude to turn raw signals into a deduped, scored candidate list."""
    signal_lines = "\n".join(
        f"[{s['source']}] ({s['engagement']} pts, {s['comments']} comments) {s['title']} | {s['url']}"
        for s in signals
    )
    prompt = (
        "You are a YouTube content strategist for a developer-focused channel. Below are raw "
        "trending signals from Hacker News, GitHub, and Reddit over the last few days.\n\n"
        "Identify the distinct AI TOOLS or PRODUCTS worth making a tutorial/demo video about. "
        "Ignore generic news, opinion pieces, model-release drama, and anything you can't screen-record a demo of.\n\n"
        "Rules:\n"
        "- Merge duplicates (the same tool mentioned across sources should be ONE candidate, and that boosts its momentum).\n"
        "- momentum_score: 0-100, based on cross-source presence + engagement. Multi-source > single-source.\n"
        "- search_keyword: the exact phrase a viewer would type on YouTube/Google to find a video about it "
        "(e.g. 'opencode tutorial', 'cursor background agents'). This is what we look up in Ahrefs next.\n"
        "- hook: a one-line video angle.\n"
        "- demoability: 'high' | 'medium' | 'low' — how easy it is to show on screen.\n\n"
        "Return ONLY a JSON array of objects with keys: "
        "name, momentum_score, search_keyword, hook, demoability, sources (array), why_now (one sentence).\n"
        "Return at most 12 candidates, highest momentum first.\n\n"
        f"Signals:\n{signal_lines}"
    )
    response = client.messages.create(
        model=model,
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(raw)


def google_autocomplete(term: str) -> list[str]:
    """Return Google search suggestions for a term (free, keyless demand proxy)."""
    try:
        resp = requests.get(
            "https://suggestqueries.google.com/complete/search",
            params={"client": "firefox", "q": term},
            headers={"User-Agent": BROWSER_UA},
            timeout=15,
        )
        resp.raise_for_status()
        return json.loads(resp.text)[1]
    except Exception:
        return []


def enrich_with_demand(candidates: list[dict]) -> None:
    """Attach Google autocomplete suggestions (name + category) to each candidate in place."""
    for c in candidates:
        name_term = c["name"].split("–")[0].split("-")[0].strip()  # bare tool name
        c["autocomplete_name"] = google_autocomplete(name_term)
        c["autocomplete_category"] = google_autocomplete(c["search_keyword"])
        time.sleep(0.3)  # be polite


def rank_and_write(candidates: list[dict], client: anthropic.Anthropic, model: str) -> list[dict]:
    """Final pass: Claude scores demand from autocomplete, ranks by demand x momentum, writes the brief."""
    blocks = []
    for c in candidates:
        blocks.append(
            f"### {c['name']} (momentum {c['momentum_score']})\n"
            f"- search_keyword: {c['search_keyword']}\n"
            f"- hook: {c['hook']}\n"
            f"- demoability: {c.get('demoability')}\n"
            f"- autocomplete[name]: {c.get('autocomplete_name')}\n"
            f"- autocomplete[category]: {c.get('autocomplete_category')}\n"
        )
    prompt = (
        "You are a YouTube strategist choosing which trending AI tool to make a video about TODAY.\n\n"
        "For each candidate you have a MOMENTUM score (0-100) and Google autocomplete suggestions for both "
        "the tool name and its category keyword. Google only autocompletes phrases people actually search, so:\n"
        "- Many ON-TOPIC suggestions (mentioning the tool, 'ai', 'tutorial', 'download', 'github', 'vs') = real DEMAND.\n"
        "- Suggestions that drift to an UNRELATED meaning (e.g. 'strix' -> 'strixhaven' Magic cards) = a namespace "
        "collision and essentially NO demand for the tool. Penalize these hard.\n\n"
        "For each candidate assign demand_score (0-100) from the autocomplete evidence, then "
        "final_score = round(sqrt(demand_score * momentum_score)) so a tool needs BOTH to win.\n"
        "Also give a one-line verdict on the content angle.\n\n"
        "Return ONLY a JSON array (sorted by final_score desc) of objects with keys: "
        "name, momentum_score, demand_score, final_score, search_keyword, hook, verdict.\n\n"
        + "\n".join(blocks)
    )
    response = client.messages.create(
        model=model,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(raw)


def write_ideas_file(ranked: list[dict], signal_count: int, output_path: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# Content Ideas — {now}",
        "",
        f"Ranked by **demand × momentum** across {signal_count} signals (Hacker News, GitHub Trending, Reddit).",
        "Demand = Google autocomplete relevance. Momentum = cross-source trending velocity.",
        "",
        "| Rank | Tool | Final | Momentum | Demand | Search keyword |",
        "|---|---|---|---|---|---|",
    ]
    for i, c in enumerate(ranked, 1):
        lines.append(
            f"| {i} | {c['name']} | **{c['final_score']}** | {c['momentum_score']} | "
            f"{c['demand_score']} | `{c['search_keyword']}` |"
        )
    lines += ["", "## Top picks", ""]
    for c in ranked[:3]:
        lines += [
            f"### {c['name']}  (score {c['final_score']})",
            f"- **Hook:** {c['hook']}",
            f"- **Verdict:** {c['verdict']}",
            f"- **Target keyword:** `{c['search_keyword']}`",
            "",
        ]
    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    refresh = "--refresh" in sys.argv
    if not refresh:
        try:
            with open(config.CONTENT_IDEAS_FILE):
                pass
            print(f"{config.CONTENT_IDEAS_FILE} already exists. Use --refresh to regenerate.")
            return
        except FileNotFoundError:
            pass

    print("1/4  Gathering momentum signals...")
    signals = fetch_hacker_news() + fetch_github() + fetch_reddit()
    if not signals:
        print("No signals gathered — check your network connection.")
        sys.exit(1)
    print(f"     Total raw signals: {len(signals)}")

    client = anthropic.Anthropic(
        api_key=config.AI_GATEWAY_API_KEY or config.ANTHROPIC_API_KEY,
        **({"base_url": "https://ai-gateway.vercel.sh"} if config.AI_GATEWAY_API_KEY else {}),
    )

    print("2/4  Distilling into candidate tools with Claude...")
    candidates = distill_candidates(signals, client, config.CLAUDE_MODEL)

    print(f"3/4  Measuring search demand via Google autocomplete ({len(candidates)} candidates)...")
    enrich_with_demand(candidates)

    print("4/4  Ranking by demand x momentum...")
    ranked = rank_and_write(candidates, client, config.CLAUDE_MODEL)

    with open(config.IDEATION_CANDIDATES_FILE, "w") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "signal_count": len(signals),
            "ranked": ranked,
            "candidates": candidates,
        }, f, indent=2)
    write_ideas_file(ranked, len(signals), config.CONTENT_IDEAS_FILE)

    print(f"\nDone. {config.CONTENT_IDEAS_FILE}")
    print("\nTop 5 by demand x momentum:")
    for c in ranked[:5]:
        print(f"  {c['final_score']:>3}  {c['name']}  (mom {c['momentum_score']} x dem {c['demand_score']})")


if __name__ == "__main__":
    main()
