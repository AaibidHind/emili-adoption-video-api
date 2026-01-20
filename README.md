# Émili — Emotional Adoption Video Generator (Full Stack)

This package delivers an **emotionally intelligent, cinematic video generator** for pet adoptions, plus **automatic social media posting** (YouTube, Instagram/Facebook via Graph API, and TikTok).

## Highlights
- Emotion-aware storyline from metadata (sad → hopeful → joyful arcs)
- Expressive AI narration (OpenAI TTS) with prosody tuning
- Smart clip selection with beat-synced pacing and gentle color grading
- Branded intro/CTA cards, captions, stickers, and music matching
- Streamlit UI for non-technical users
- FastAPI for programmatic generation & publishing
- Social auto-posting adapters (YouTube, IG/FB, TikTok)
- Engagement tracking stubs (local JSON) for dashboards

> **Note:** You must provide API keys in `.env` (see `.env.sample`). No secrets are shipped.

---

## Quick Start

### 1) Install
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Configure
Copy `.env.sample` to `.env` and fill values:
```
OPENAI_API_KEY=...
YOUTUBE_API_KEY=...
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...

FB_PAGE_ID=...
FB_ACCESS_TOKEN=...
IG_BUSINESS_ID=...
IG_ACCESS_TOKEN=...

TIKTOK_CLIENT_KEY=...
TIKTOK_CLIENT_SECRET=...
TIKTOK_ACCESS_TOKEN=...
```

### 3) Run Streamlit UI
```bash
streamlit run app.py
```

### 4) Run API server
```bash
uvicorn server:app --reload --port 8080
```

---

## Project Layout

```
.
├─ app.py                 # Streamlit UI
├─ server.py              # FastAPI API
├─ backend/
│  ├─ config.py           # Pydantic settings from .env
│  ├─ story.py            # Storyline + captions from metadata
│  ├─ audio.py            # OpenAI TTS + VO post-processing
│  ├─ emotion.py          # Lightweight emotion heuristics
│  ├─ edit.py             # MoviePy assembly + pacing + grading
│  ├─ branding.py         # Intro/CTA/sticker overlays
│  ├─ generate.py         # Orchestration (one-call entry point)
│  └─ social/
│     ├─ publisher.py     # Unified publishing entry
│     ├─ youtube.py       # YouTube Data API v3 upload
│     ├─ facebook.py      # FB/IG Graph API publishing
│     └─ tiktok.py        # TikTok upload
├─ assets/
│  ├─ branding/logo.txt   # Placeholder (use your PNG here)
│  └─ music/soft/soft_demo.txt
├─ examples/pets/fido/
│  ├─ metadata.json
│  ├─ voiceover.txt       # Placeholder text VO (optional)
│  └─ clips/              # Put your .mp4 clips here
├─ .env.sample
├─ requirements.txt
├─ Dockerfile
└─ README.md
```

---

## Example API Calls

**Generate video**
```bash
curl -X POST http://localhost:8080/generate -H "Content-Type: application/json" -d '{
  "pet_dir": "examples/pets/fido",
  "tone": "auto",
  "aspect": "vertical",
  "target_duration": 45,
  "out": "out/fido_vertical.mp4"
}'
```

**Publish to platforms**
```bash
curl -X POST http://localhost:8080/publish -H "Content-Type: application/json" -d '{
  "video_path": "out/fido_vertical.mp4",
  "title": "Meet Fido — A Gentle Soul",
  "description": "Adopt Fido today at emili.pet/adoptions/fido",
  "hashtags": ["adopt", "dog", "rescue"],
  "targets": ["youtube","instagram","facebook","tiktok"]
}'
```

---

## Notes & Limits
- OpenAI TTS requires `OPENAI_API_KEY`.
- Social APIs often require OAuth flows. This repo assumes you’ve obtained long-lived tokens/server-to-server creds and places them in `.env`. Check each adapter for comments.
- Video rendering relies on `ffmpeg`. Ensure it’s installed (Dockerfile handles this).

Happy adoptions! 🐶🐱


### Choosing OpenAI models
- `OPENAI_CHAT_MODEL` (default `gpt-4o`) drives the storytelling (you can set `gpt-4`, `gpt-4.1`, etc.).
- `OPENAI_TTS_MODEL` (default `tts-1`) drives narration TTS (you can use `tts-1-hd` or other TTS models).
