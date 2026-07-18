# Ideation Stage (`ideate.py`)

Pre-production stage that decides **what to record**. Runs before Stage 1. Fully self-contained and keyless (reuses only `AI_GATEWAY_API_KEY` for Claude).

## The strategy: demand × momentum

"Most trending" is ambiguous, so the script separates two signals and multiplies them:

- **Momentum** — is it spiking *right now*? Sources: Hacker News points (last 72h), GitHub Trending stars-**this-week** velocity, Reddit hot (best-effort).
- **Demand** — are people actually *searching* for it? Proxy: Google autocomplete. Google only suggests phrases people really search, and it exposes namespace collisions (`strix` → "strixhaven" Magic cards = ~0 tool demand).

`final_score = round(sqrt(demand_score × momentum_score))` — a tool needs BOTH to win. This deliberately demotes brand-new repos with no search footprint and demotes generic-named tools whose autocomplete drifts off-topic.

## Why not GitHub stars alone?

Total stars measure cumulative fame, not this week's momentum, and miss every closed-source tool (Cursor, Claude Code, Devin have no repo to star). The script uses GitHub Trending **velocity** as one momentum input among several, never as the sole signal.

## Pipeline (4 steps, one run)

1. **Gather** — `fetch_hacker_news()`, `fetch_github()`, `fetch_reddit()` → raw signals with `{source, title, engagement, comments, url}`.
2. **Distill** — Claude dedupes signals into ≤12 candidate tools with `momentum_score`, `search_keyword`, `hook`, `demoability`, `why_now`.
3. **Enrich** — `google_autocomplete()` for each candidate's name + category keyword.
4. **Rank & write** — Claude scores `demand_score` from autocomplete relevance, computes `final_score`, writes `content-ideas.md` (ranked table + top-3 briefs) and `candidates.json` (full data).

## Sources & reliability

| Source | Auth | Notes |
|---|---|---|
| Hacker News (Algolia) | none | Reliable. Stories >`IDEATION_HN_MIN_POINTS` in last `IDEATION_HN_LOOKBACK_HOURS`. |
| GitHub Trending | none | Scrapes `/trending?since=weekly` for stars-this-week. Set `GITHUB_TOKEN` to use authenticated new-repo search instead. |
| Reddit | OAuth | Blocks server IPs without OAuth (403). Best-effort; degrades gracefully. |
| Google autocomplete | none | Demand proxy. Reliable. |

## Config (`config.py`)

| Variable | Default | Effect |
|---|---|---|
| `IDEATION_GITHUB_LOOKBACK_DAYS` | 30 | "New & hot" window (authenticated search path only) |
| `IDEATION_HN_LOOKBACK_HOURS` | 72 | HN recency window |
| `IDEATION_HN_MIN_POINTS` | 30 | Drop low-signal HN stories |
| `IDEATION_SUBREDDITS` | LocalLLaMA, artificial, OpenAI, ChatGPT | Reddit subs polled |
| `IDEATION_GITHUB_TOKEN` | env `GITHUB_TOKEN` | Optional; enables authenticated search path |

## Optional upgrade: real search volume via Ahrefs

Google autocomplete is a demand *proxy*. For exact monthly search volume + keyword difficulty, use the Ahrefs MCP `keywords-explorer-overview` in-session on the distilled candidates, then rank by `volume × momentum`. Requires an Ahrefs plan with Keywords Explorer API access (the currently connected account returns "Insufficient plan").

## Tuning ideas

- Add more subreddits or a YouTube Data API competition check to the enrichment step.
- Weight the final score toward demand (evergreen/searchable videos) or momentum (first-mover on fresh launches) by editing the `rank_and_write()` prompt.
- Bump `distill_candidates` beyond 12 candidates for a wider net.
