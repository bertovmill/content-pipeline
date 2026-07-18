import os
from pathlib import Path

PROJECT_DIR = str(Path(__file__).parent)
RAW_FRAMES_DIR = os.path.join(PROJECT_DIR, "frames_raw")
FRAMES_DIR = os.path.join(PROJECT_DIR, "frames")
CAPTIONS_FILE = os.path.join(PROJECT_DIR, "captions.json")
AUDIO_TTS_DIR = os.path.join(PROJECT_DIR, "audio", "tts")
AUDIO_SFX_DIR = os.path.join(PROJECT_DIR, "audio", "sfx")
AUDIO_MIXED_DIR = os.path.join(PROJECT_DIR, "audio", "mixed")
AUDIO_MUSIC_FILE = os.path.join(PROJECT_DIR, "audio", "background_music.mp3")
TIMESTAMPS_DIR = os.path.join(PROJECT_DIR, "audio", "timestamps")
OUTPUT_VIDEO = os.path.join(PROJECT_DIR, "output.mp4")
THUMBNAIL_FILE = os.path.join(PROJECT_DIR, "thumbnail.png")
HEADSHOT_FILE = os.path.join(PROJECT_DIR, "berto-mill.png")
YOUTUBE_FILE = os.path.join(PROJECT_DIR, "youtube.md")
SRT_FILE = os.path.join(PROJECT_DIR, "captions.srt")
ARTICLE_FILE = os.path.join(PROJECT_DIR, "article.md")

# Ideation stage (pre-production) — runs before you record.
# ideate.py gathers momentum signals -> candidates.json.
# Claude then enriches with Ahrefs search volume -> content-ideas.md.
IDEATION_CANDIDATES_FILE = os.path.join(PROJECT_DIR, "candidates.json")
CONTENT_IDEAS_FILE = os.path.join(PROJECT_DIR, "content-ideas.md")
IDEATION_GITHUB_LOOKBACK_DAYS = 30    # "new & hot" repo window
IDEATION_HN_LOOKBACK_HOURS = 72       # HN front-page recency window
IDEATION_HN_MIN_POINTS = 30           # ignore low-signal HN stories
IDEATION_SUBREDDITS = ["LocalLLaMA", "artificial", "OpenAI", "ChatGPT"]
# Optional: a GitHub token raises the search-API rate limit and enables AI-filtered
# new-repo search. Without it, ideate.py scrapes the public Trending page (no auth).
IDEATION_GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

FRAME_INTERVAL_SECONDS = 10
SIMILARITY_THRESHOLD = 0.95

# Speed up the source recording before frame extraction.
# 3.0 = 3x faster footage in the final video. Set to 1.0 to disable.
SOURCE_SPEED_MULTIPLIER = 3.0
SPED_UP_VIDEO = os.path.join(PROJECT_DIR, f"source_{int(SOURCE_SPEED_MULTIPLIER)}x.mp4")

CLAUDE_MODEL = "anthropic/claude-sonnet-4.6"
CAPTION_PROMPT = (
    "You are narrating a YouTube tutorial for developers. Write 2-3 sentences of spoken voiceover "
    "for this screen, as if you're the instructor walking the viewer through exactly what you're doing and why. "
    "Use second person ('we' or 'you'), present tense, and a friendly but confident tone. "
    "Be specific about what tool, command, or step is visible. "
    "Example style: 'Now we're going to open the terminal and install the LangChain package. "
    "You can see here we're using npm to add it to our project — this gives us access to all the core LangChain primitives.'"
)

ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
MUSIC_TRACK_PATH = os.environ.get("MUSIC_TRACK_PATH", "")
MUSIC_VOLUME = 0.15

# Vercel AI Gateway (preferred) — set AI_GATEWAY_API_KEY to route through gateway
# Falls back to direct Anthropic if AI_GATEWAY_API_KEY is not set
AI_GATEWAY_API_KEY = os.environ.get("AI_GATEWAY_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
