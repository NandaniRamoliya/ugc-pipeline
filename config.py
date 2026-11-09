import json
import os
from zoneinfo import ZoneInfo

try:  # lets you test locally with a .env file
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def env(name, default=None):
    val = os.getenv(name) or default
    if val is None:
        raise RuntimeError(f"Missing environment variable: {name}")
    return val


TZ = ZoneInfo("Asia/Kolkata")

# ---- Credentials (GitHub Secrets) ----
GEMINI_API_KEY = env("GEMINI_API_KEY")
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-3.8-flash")
GOOGLE_SA_INFO = json.loads(env("GOOGLE_SA_JSON"))
SHEET_ID = env("SHEET_ID")
DRIVE_INBOX_FOLDER_ID = env("DRIVE_INBOX_FOLDER_ID")
TG_TOKEN = env("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = str(env("TELEGRAM_CHAT_ID"))
IG_USER_ID = env("IG_USER_ID")
IG_TOKEN_SEED = env("IG_ACCESS_TOKEN")
IG_HOST = env("IG_GRAPH_HOST", "graph.instagram.com")
IG_VERSION = env("IG_API_VERSION", "v22.0")
env("CLOUDINARY_URL")  # read automatically by the cloudinary library

# ---- Content settings ----
IDEAS_PER_WEEK = int(env("IDEAS_PER_WEEK", "4"))
POST_SLOTS = [(1, "19:00"), (3, "19:00"), (5, "12:00")]  # Mon=0 … Sun=6, IST
VOICE_MODE = env("VOICE_MODE", "tts")       # "tts" = AI voiceover | "original" = keep clip audio
TTS_VOICE = env("TTS_VOICE", "en-IN-NeerjaNeural")
TTS_RATE = "+8%"
MUSIC_VOLUME = 0.12

ACCOUNT_BRIEF = """
Account: @ugcwithnandani, a FACELESS UGC creator account (hands, products, surfaces; never a face).
Purpose: a portfolio that attracts brands for paid UGC. Every reel should look like an ad a brand would pay for.
Audience: Indian viewers 18-32, mobile-first, into skincare, beauty, lifestyle and gadgets.
Voice: friendly, honest, specific, a little playful. Simple English; light Hinglish words are fine.
Rules:
- Every shot must be filmable at home on a phone by one person, hands only.
- The hook must stop the scroll within 2 seconds.
- No medical claims, no invented results, no fake discounts. Speak as "I".
- Say the product name at least once in the voiceover.
"""

