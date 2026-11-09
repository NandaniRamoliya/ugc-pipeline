import json
import time

from google import genai
from google.genai import types

from config import ACCOUNT_BRIEF, GEMINI_API_KEY, GEMINI_MODEL

_client = genai.Client(api_key=GEMINI_API_KEY)

ANGLES = [
    "problem → solution", "honest first impression", "unboxing", "how I use it (routine)",
    "3 things I wish I knew", "ASMR texture close-ups", "visual before vs after (no claims)",
    "vs what I used before", "aesthetic vanity/desk setup",
]

RULES = """
Script rules:
- 4 to 7 shots, total 15-35 seconds.
- Shot 1's on_screen_text IS the hook (max 8 words).
- Other on_screen_text: max 7 words, or "" if not needed.
- voiceover per shot: one natural spoken sentence, max 18 words.
- visual: exact filming direction (angle, hand action, background, light),
  e.g. "Top-down, fingertip swipes cream, white bedsheet, window light".
- caption: 2-4 short lines ending with a question or CTA, max 500 characters, no hashtags.
- hashtags: 4-6, niche + product category.
"""

SCHEMA = """Return only JSON in this shape:
{"ideas": [{"product_id": "id from the list", "angle": "...", "hook": "...",
  "shots": [{"visual": "...", "on_screen_text": "...", "voiceover": "...", "seconds": 4}],
  "caption": "...", "hashtags": ["#..."]}]}"""


def _json(prompt, temperature=0.9):
    last = None
    for attempt in range(3):
        try:
            resp = _client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json",
                                                   temperature=temperature))
            return json.loads(resp.text)
        except Exception as e:  # rate limits / bad JSON → retry
            last = e
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Gemini failed: {last}")


def _clean(data):
    ideas = data.get("ideas", []) if isinstance(data, dict) else data
    good = []
    for i in ideas:
        try:
            if not (2 <= len(i["shots"]) <= 10 and i["hook"] and i["caption"]):
                continue
            tags = i.get("hashtags") or []
            if isinstance(tags, str):
                tags = tags.split()
            i["hashtags"] = ["#" + t.lstrip("#") for t in tags][:6]
            i["product_id"] = str(i["product_id"])
            i.setdefault("angle", "")
            for s in i["shots"]:
                s["seconds"] = float(s.get("seconds") or 3)
            good.append(i)
        except (KeyError, TypeError, ValueError):
            continue
    return good


def generate_ideas(products, n, learnings="", avoid_hooks=()):
    prompt = f"""{ACCOUNT_BRIEF}
Create {n} different UGC Reel scripts. Use ONLY these products (refer to them by product_id),
spread across products and use different angles:
{json.dumps(products, ensure_ascii=False, indent=1)}

Angle options: {", ".join(ANGLES)}
{RULES}
What has worked on this account recently:
{learnings or "No data yet."}

Do not reuse these recent hooks: {json.dumps(list(avoid_hooks), ensure_ascii=False)}

{SCHEMA}"""
    return _clean(_json(prompt))


def rewrite_idea(product, old_hook, old_angle, note=""):
    prompt = f"""{ACCOUNT_BRIEF}
Write ONE new UGC Reel script for this product:
{json.dumps(product, ensure_ascii=False)}
The previous script (angle "{old_angle}", hook "{old_hook}") was rejected. Use a different angle and hook.
{("Creator's direction: " + note) if note else ""}
{RULES}
{SCHEMA}
Return exactly one idea in the list."""
    ideas = _clean(_json(prompt))
    if not ideas:
        raise RuntimeError("AI returned no usable script")
    return ideas[0]


def weekly_learnings(posts):
    prompt = f"""You analyse a faceless UGC Instagram account. Here are recent reels with metrics:
{json.dumps(posts, ensure_ascii=False, indent=1)}

Return JSON: {{"learnings": ["3-5 specific, actionable bullets about hooks, angles, length, products"],
"report": "a plain-language weekly summary under 120 words"}}"""
    return _json(prompt, temperature=0.4)

