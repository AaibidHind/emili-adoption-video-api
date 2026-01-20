from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import List, Optional, Dict, Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import PetProjectConfig
from backend.generate import generate_video
from backend.social import post_to_platform

app = FastAPI(title="Emili Emotional Adoption Video Generator API")

OUT_DIR = Path("out")
OUT_DIR.mkdir(exist_ok=True)
app.mount("/out", StaticFiles(directory=str(OUT_DIR)), name="out")

ASSETS_DIR = Path("assets")
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR), html=False), name="static")

# -----------------------
# Legal pages (optional)
# -----------------------
@app.get("/terms", response_class=HTMLResponse)
def terms():
    p = Path("legal/terms.html")
    if not p.exists():
        return HTMLResponse("<h2>Terms of Service</h2><p>Placeholder.</p>", status_code=200)
    return p.read_text(encoding="utf-8")

@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    p = Path("legal/privacy.html")
    if not p.exists():
        return HTMLResponse("<h2>Privacy Policy</h2><p>Placeholder.</p>", status_code=200)
    return p.read_text(encoding="utf-8")

@app.get("/{filename}.txt")
def serve_txt(filename: str):
    file_path = STATIC_DIR / f"{filename}.txt"
    if file_path.exists():
        return FileResponse(str(file_path), media_type="text/plain")
    raise HTTPException(status_code=404, detail="File not found")

# --------------------------------------------------------------------
# Shared OAuth state + in-memory token stores (TEMP: replace with DB)
# --------------------------------------------------------------------
OAUTH_STATE: Dict[str, bool] = {}

TOKENS: Dict[str, Any] = {
    "tiktok": None,  # will store last tiktok token response
    "meta": None,    # will store last meta token response
}

# =========================
# TikTok OAuth (existing)
# =========================
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
TIKTOK_REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI")

TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

@app.get("/auth/tiktok/start")
def tiktok_auth_start():
    if not TIKTOK_CLIENT_KEY or not TIKTOK_REDIRECT_URI:
        raise HTTPException(
            status_code=500,
            detail="Missing TIKTOK_CLIENT_KEY or TIKTOK_REDIRECT_URI in environment.",
        )

    state = secrets.token_urlsafe(16)
    OAUTH_STATE[state] = True

    params = {
        "client_key": TIKTOK_CLIENT_KEY,
        "response_type": "code",
        "scope": "user.info.basic,video.publish",
        "redirect_uri": TIKTOK_REDIRECT_URI,
        "state": state,
    }

    url = requests.Request("GET", TIKTOK_AUTH_URL, params=params).prepare().url
    return RedirectResponse(url)

@app.get("/auth/tiktok/callback")
def tiktok_auth_callback(code: str | None = None, state: str | None = None):
    if not code or not state or state not in OAUTH_STATE:
        return JSONResponse({"error": "Invalid OAuth response"}, status_code=400)

    if not TIKTOK_CLIENT_KEY or not TIKTOK_CLIENT_SECRET or not TIKTOK_REDIRECT_URI:
        raise HTTPException(
            status_code=500,
            detail="Missing TikTok env vars: TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET / TIKTOK_REDIRECT_URI.",
        )

    data = {
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": TIKTOK_REDIRECT_URI,
    }

    token_res = requests.post(
        TIKTOK_TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )

    TOKENS["tiktok"] = token_res.json()

    return {
        "message": "TikTok account connected successfully",
        "tiktok_response": TOKENS["tiktok"],
    }

# =========================
# META OAuth (Facebook/IG)
# =========================
META_APP_ID = os.getenv("META_APP_ID") or os.getenv("FACEBOOK_APP_ID")
META_APP_SECRET = os.getenv("META_APP_SECRET") or os.getenv("FACEBOOK_APP_SECRET")
META_REDIRECT_URI = os.getenv("META_REDIRECT_URI") or os.getenv("FACEBOOK_REDIRECT_URI")

# OAuth endpoints
META_AUTH_URL = "https://www.facebook.com/v19.0/dialog/oauth"
META_TOKEN_URL = "https://graph.facebook.com/v19.0/oauth/access_token"

# Permissions:
# - Minimal dev (login): "public_profile,email"
# - For Pages + IG publishing (later app review):
#   pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish
META_SCOPES = os.getenv(
    "META_SCOPES",
    "public_profile,email"
)

@app.get("/auth/meta/start")
def meta_auth_start():
    if not META_APP_ID or not META_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="Missing META_APP_ID or META_REDIRECT_URI in environment.")

    state = secrets.token_urlsafe(16)
    OAUTH_STATE[state] = True

    params = {
        "client_id": META_APP_ID,
        "redirect_uri": META_REDIRECT_URI,
        "state": state,
        "response_type": "code",
        "scope": META_SCOPES,
    }

    url = requests.Request("GET", META_AUTH_URL, params=params).prepare().url
    return RedirectResponse(url)

@app.get("/auth/meta/callback")
def meta_auth_callback(code: str | None = None, state: str | None = None):
    if not code or not state or state not in OAUTH_STATE:
        return JSONResponse({"error": "Invalid OAuth response"}, status_code=400)

    if not META_APP_ID or not META_APP_SECRET or not META_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="Missing META_APP_ID / META_APP_SECRET / META_REDIRECT_URI.")

    params = {
        "client_id": META_APP_ID,
        "client_secret": META_APP_SECRET,
        "redirect_uri": META_REDIRECT_URI,
        "code": code,
    }

    token_res = requests.get(META_TOKEN_URL, params=params, timeout=30)
    data = token_res.json()

    TOKENS["meta"] = data

    return {
        "message": "Meta account connected successfully",
        "meta_response": data,
        "next": "If you need Pages/Instagram publishing, request the required permissions and generate a Page access token.",
    }

@app.get("/auth/meta/status")
def meta_status():
    return {"meta_token_present": TOKENS["meta"] is not None, "meta_token": TOKENS["meta"]}


# =========================
# Video generation / publish
# =========================
class GenRequest(BaseModel):
    pet_dir: str
    logo_path: Optional[str] = "assets/branding/logo.png"
    music_dir: Optional[str] = "assets/music"
    tone: str = "auto"
    fps: int = 30
    target_duration: int = 45
    aspect: str = "vertical"
    use_tts: bool = True
    transcribe_vo: bool = True
    out: str = "out/out.mp4"
    tts_voice: str = "alloy"
    tts_speed: float = 1.0

class PubRequest(BaseModel):
    video_path: str
    title: str
    description: str
    hashtags: Optional[List[str]] = None
    targets: Optional[List[str]] = None

@app.post("/generate")
def generate(req: GenRequest):
    cfg = PetProjectConfig(
        pet_dir=Path(req.pet_dir),
        logo_path=Path(req.logo_path) if req.logo_path else None,
        music_dir=Path(req.music_dir) if req.music_dir else None,
        aspect=req.aspect,
        target_duration=req.target_duration,
        fps=req.fps,
        use_tts=req.use_tts,
        tts_speed=req.tts_speed,
        tts_voice=req.tts_voice,
        transcribe_vo=req.transcribe_vo,
        tone=req.tone,
        auto_post=False,
    )

    out_path = Path(req.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    result = generate_video(cfg, out_path)

    return {
        "success": result.success,
        "message": result.message,
        "outfile": str(result.outfile) if result.outfile else None,
        "duration": result.duration,
        "tone_arc": result.tone_arc,
        "story_title": result.story_title,
    }

@app.post("/publish")
def publish(req: PubRequest):
    video_path = Path(req.video_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Video not found: {video_path}")

    hashtags = req.hashtags or []
    targets = req.targets or ["youtube"]

    if hashtags:
        hashtag_str = " ".join(f"#{h}" for h in hashtags)
        full_description = f"{req.description.rstrip()}\n\n{hashtag_str}"
    else:
        full_description = req.description

    results = []
    for platform in targets:
        res = post_to_platform(
            platform=platform,
            video_path=video_path,
            title=req.title,
            description=full_description,
        )
        results.append(res)

    return {"results": results}
