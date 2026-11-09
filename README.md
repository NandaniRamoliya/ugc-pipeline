# UGC Pipeline

Fully-automated, **serverless** Instagram Reels pipeline for a faceless UGC creator account.  
Runs on **GitHub Actions** every 30 minutes. Google Sheets is the database. No server, no Docker.

```
Monday 9 AM ──► Gemini writes 4 scripts from your Products sheet ──► Telegram [Approve / Rewrite / Drop]
                                                                          │ Approve
                                                                          ▼
                                     Drive folder "UGC-0007 · Product" is created ◄── you upload clips
                                                                          │ (all clips present, or /go)
                                                                          ▼
              FFmpeg builds the reel: 9:16 crop + caption overlays + AI voiceover + music + cover
                                                                          ▼
                                   Telegram preview [Approve & schedule / Re-film / Drop]
                                                                          ▼
                       Next free slot (Tue/Thu/Sat) ──► Instagram Reel published ──► link sent to you
                                                                          ▼
                        Weekly: insights ──► Gemini learnings ──► fed into next week's scripts
```

## Repo layout

```
ugc-pipeline/
├── .github/workflows/pipeline.yml   ← GitHub Actions cron
├── assets/music/                    ← drop royalty-free .mp3 files here
├── config.py                        ← all env vars & content settings
├── store.py                         ← Google Sheets ORM
├── ai.py                            ← Gemini script generation & weekly learnings
├── tg.py                            ← Telegram bot
├── drive.py                         ← Google Drive folder creation & clip download
├── video.py                         ← FFmpeg reel assembly, TTS, caption overlays
├── cloud.py                         ← Cloudinary upload → public URL for Instagram
├── ig.py                            ← Instagram Graph API
├── main.py                          ← orchestrator: tick / weekly / ideate
└── requirements.txt
```

## One-time setup (~1–2 hours)

### 1. Google Cloud (free)
Create a project, enable **Google Sheets API** and **Google Drive API**.  
Create a **service account** and download its JSON key.

### 2. Google Sheet
Create a blank Sheet and share it with the service account email as **Editor**.  
Copy the sheet ID from the URL (the long string between `/d/` and `/edit`).  
The tabs `Content`, `Products`, and `State` are created automatically on the first run.

### 3. Google Drive — UGC Inbox folder
Create a folder called `UGC Inbox`, share it with the service account as **Editor**,  
and copy its ID from the URL (the string after `/folders/`).

### 4. Gemini API key
Get a free key from [Google AI Studio](https://aistudio.google.com/).  
If `gemini-2.5-flash` has been retired, set the `GEMINI_MODEL` variable to the current Flash model name.

### 5. Telegram bot
Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.  
Send your bot "hi", then open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser  
and copy `chat.id`. Do this **before** the first run — the pipeline consumes these updates.

### 6. Cloudinary (free plan)
Copy the `CLOUDINARY_URL` from your dashboard (format: `cloudinary://key:secret@cloud`).  
Instagram requires a public video URL; Drive links don't work.

### 7. Instagram
- Switch your account to **Creator or Business**.
- On [developers.facebook.com](https://developers.facebook.com), create an app with  
  **Instagram API with Instagram Login**, add your account as a tester, and grant  
  `instagram_business_basic`, `instagram_business_content_publish`, `instagram_business_manage_insights`.
- Generate a long-lived token. Call  
  `https://graph.instagram.com/me?fields=user_id,username&access_token=…`  
  and use the returned `user_id` as `IG_USER_ID`.

### 8. GitHub repo
- Create a **private** repo and push the code.
- Under **Settings → Secrets → Actions**, add these nine secrets:

| Secret | Value |
|--------|-------|
| `GEMINI_API_KEY` | Gemini API key |
| `GOOGLE_SA_JSON` | Entire service account JSON (paste the whole file) |
| `SHEET_ID` | Google Sheet ID |
| `DRIVE_INBOX_FOLDER_ID` | Drive folder ID |
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your chat ID |
| `CLOUDINARY_URL` | `cloudinary://key:secret@cloud` |
| `IG_USER_ID` | Instagram numeric user ID |
| `IG_ACCESS_TOKEN` | Long-lived Instagram token |

- Run the workflow manually with task `ideate` to test.

### 9. Products tab
Add the products you actually own, one per row:

```
product_id | name                        | brand      | category | key_benefits               | notes          | status
1          | Minimalist 10% Niacinamide  | Minimalist | skincare | lightweight, non-sticky    | own it 3 weeks | available
```

## Local testing

```bash
cp .env.example .env        # fill in your real values
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
python main.py ideate
```

## Telegram commands

| Command | What it does |
|---------|-------------|
| `/status` | Pipeline status count by stage |
| `/ideas 2` | Generate N new scripts immediately |
| `/rewrite UGC-0003 make it funnier` | Rewrite a script with a note |
| `/go UGC-0003` | Force-build with clips uploaded so far |
| `/caption UGC-0003 New caption text` | Edit the caption before publishing |
| `/when UGC-0003 2026-11-20 19:00` | Reschedule a reel |
| `/retry UGC-0003` | Retry a failed Instagram publish |

## Content settings (edit in `config.py`)

| Variable | Default | Meaning |
|----------|---------|---------|
| `IDEAS_PER_WEEK` | `4` | Scripts generated each Monday |
| `POST_SLOTS` | Tue/Thu 7 PM, Sat 12 PM IST | Publishing schedule |
| `VOICE_MODE` | `tts` | `tts` = AI voiceover, `original` = keep clip audio |
| `TTS_VOICE` | `en-IN-NeerjaNeural` | Edge-TTS voice |
| `MUSIC_VOLUME` | `0.12` | Background music level (0–1) |

## Things to know

- **Response time:** Button taps are processed at the next run — up to 30 min delay. GitHub's cron can also run a few minutes late.
- **Actions minutes:** A 30-min tick uses ~1,500 of the 2,000 free monthly minutes on a private repo. Keep the interval at 30 min.
- **Voiceover:** `edge-tts` uses Microsoft's unofficial endpoint and can break without notice. If it does, set `VOICE_MODE=original`.
- **Phone tips:** Turn off HDR on iPhone; use JPG not HEIC; film vertically.
- **Security:** The refreshed Instagram token is stored in the `State` tab — keep the Sheet private.
- **Drive folders:** If the service account can't create folders, Telegram tells you to create one named `UGC-0007` yourself.
