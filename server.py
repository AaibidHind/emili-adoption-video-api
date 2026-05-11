from __future__ import annotations

from fastapi.staticfiles import StaticFiles

import asyncio
import websockets
from fastapi import WebSocket, UploadFile, File

import os
import secrets
import json
import urllib.parse
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any

import httpx
import requests
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.config import PetProjectConfig
from backend.generate import generate_video
from backend.social_main import post_to_platform

app = FastAPI(title="Emili Adoption Video API")

STREAMLIT_BASE = "https://emili-streamlit.onrender.com"

TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
TIKTOK_REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI")
TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

META_APP_ID = os.getenv("META_APP_ID") or os.getenv("FACEBOOK_APP_ID")
META_APP_SECRET = os.getenv("META_APP_SECRET") or os.getenv("FACEBOOK_APP_SECRET")
META_REDIRECT_URI = os.getenv("META_REDIRECT_URI") or os.getenv("FACEBOOK_REDIRECT_URI")
META_AUTH_URL = "https://www.facebook.com/v19.0/dialog/oauth"
META_TOKEN_URL = "https://graph.facebook.com/v19.0/oauth/access_token"
OAUTH_STATE_META: Dict[str, bool] = {}

TOKEN_FILE = Path("tokens.json")

def load_tokens() -> Dict[str, Any]:
    if TOKEN_FILE.exists():
        try:
            return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"tiktok": None, "meta": None}

def save_tokens(tokens: Dict[str, Any]):
    try:
        TOKEN_FILE.write_text(json.dumps(tokens), encoding="utf-8")
    except Exception as e:
        print(f"Token save error: {e}")

TOKENS: Dict[str, Any] = load_tokens()

OUT_DIR = Path("out").resolve()
OUT_DIR.mkdir(parents=True, exist_ok=True)

STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job("interval", hours=20)
async def refresh_tiktok_token():
    tiktok_data = TOKENS.get("tiktok")
    if not tiktok_data:
        return
    refresh_token = tiktok_data.get("refresh_token")
    if not refresh_token:
        return
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                TIKTOK_TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "client_key": TIKTOK_CLIENT_KEY,
                    "client_secret": TIKTOK_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                }
            )
            data = r.json()
            if "access_token" in data:
                TOKENS["tiktok"] = data
                save_tokens(TOKENS)
                os.environ["TIKTOK_ACCESS_TOKEN"] = data["access_token"]
                print("[scheduler] TikTok token refreshed")
            else:
                print("[scheduler] TikTok refresh failed:", data)
    except Exception as e:
        print(f"[scheduler] TikTok refresh error: {e}")

@scheduler.scheduled_job("interval", days=50)
async def refresh_meta_token():
    meta_data = TOKENS.get("meta")
    if not meta_data or "access_token" not in meta_data:
        return
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://graph.facebook.com/v19.0/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": META_APP_ID,
                    "client_secret": META_APP_SECRET,
                    "fb_exchange_token": meta_data["access_token"],
                }
            )
            data = r.json()
            if "access_token" in data:
                TOKENS["meta"] = data
                save_tokens(TOKENS)
                print("[scheduler] Meta token refreshed")
            else:
                print("[scheduler] Meta refresh failed:", data)
    except Exception as e:
        print(f"[scheduler] Meta refresh error: {e}")

@app.on_event("startup")
async def start_scheduler():
    scheduler.start()

@app.on_event("shutdown")
async def stop_scheduler():
    scheduler.shutdown()

app.mount("/out", StaticFiles(directory=str(OUT_DIR)), name="out")

ASSETS_DIR = Path("assets")
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

LEGAL_DIR = Path("legal")
if LEGAL_DIR.exists():
    app.mount("/legal", StaticFiles(directory="legal", html=True), name="legal")

def _landing_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Emili - Adoption Video Generator</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Arial,sans-serif;color:#111}
.hero{padding:60px 32px 48px;text-align:center;border-bottom:1px solid #eee}
.hero h1{font-size:28px;font-weight:600;margin-bottom:14px}
.hero p{font-size:16px;color:#555;max-width:520px;margin:0 auto 32px;line-height:1.6}
.btn{display:inline-flex;align-items:center;gap:10px;padding:14px 28px;background:#fe2c55;color:white;border-radius:8px;font-size:16px;font-weight:600;text-decoration:none}
.features{display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid #eee}
.feature{padding:28px 24px;border-right:1px solid #eee}
.feature:last-child{border-right:none}
.feature h3{font-size:15px;font-weight:600;margin-bottom:8px}
.feature p{font-size:13px;color:#666;line-height:1.5}
.steps{padding:48px 32px;max-width:600px;margin:0 auto}
.steps h2{font-size:20px;font-weight:600;margin-bottom:28px;text-align:center}
.step{display:flex;gap:16px;margin-bottom:20px}
.num{width:32px;height:32px;border-radius:50%;background:#f5f5f5;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:600;flex-shrink:0}
.step h4{font-size:14px;font-weight:600;margin-bottom:4px}
.step p{font-size:13px;color:#666;line-height:1.5}
.cta{padding:40px 32px;text-align:center;border-top:1px solid #eee;border-bottom:1px solid #eee}
.cta p{font-size:15px;color:#555;margin-bottom:20px}
.footer{padding:20px 32px;display:flex;justify-content:space-between;align-items:center}
.footer p{font-size:12px;color:#999}
.footer a{font-size:12px;color:#666;text-decoration:none;margin-left:16px}
</style>
</head>
<body>
<div class="hero">
  <h1>Emili adoption video generator</h1>
  <p>We help animal shelters create emotional adoption videos and publish them automatically to TikTok, Instagram, YouTube, and Facebook so more animals find homes, faster.</p>
  <a href="/auth/tiktok/start" class="btn">Connect your TikTok account</a>
</div>
<div class="features">
  <div class="feature">
    <h3>AI-generated videos</h3>
    <p>GPT-4 writes an emotional adoption script, TTS narrates it, and the video is assembled automatically.</p>
  </div>
  <div class="feature">
    <h3>One-click publishing</h3>
    <p>Publish directly to TikTok, Instagram, YouTube, and Facebook from a single interface.</p>
  </div>
  <div class="feature">
    <h3>Built for shelters</h3>
    <p>Used by over 150 municipalities and shelters across Canada. Available in English and French.</p>
  </div>
</div>
<div class="steps">
  <h2>How shelter administrators connect TikTok</h2>
  <div class="step">
    <div class="num">1</div>
    <div><h4>Click "Connect your TikTok account"</h4><p>You will be redirected to TikTok's secure authorization page.</p></div>
  </div>
  <div class="step">
    <div class="num">2</div>
    <div><h4>Log in and authorize Emili</h4><p>Grant Emili permission to upload videos to your TikTok profile on your behalf.</p></div>
  </div>
  <div class="step">
    <div class="num">3</div>
    <div><h4>Generate and publish</h4><p>Use the Emili dashboard to generate adoption videos and post them directly to TikTok with one click.</p></div>
  </div>
</div>
<div class="cta">
  <p>Ready to help more animals find homes?</p>
  <a href="/auth/tiktok/start" class="btn">Connect TikTok account</a>
</div>
<div class="footer">
  <p>Emili Tracking Solutions Inc. — Montreal, QC, Canada</p>
  <div><a href="/terms">Terms</a><a href="/privacy">Privacy</a><a href="/delete-data">Data deletion</a></div>
</div>
</body>
</html>"""

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def landing_page():
    return HTMLResponse(_landing_html())

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    dest = OUT_DIR / file.filename
    with open(dest, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    shutil.copy(dest, STATIC_DIR / file.filename)
    return {"filename": file.filename, "url": f"{os.getenv('SOCIAL_PUBLIC_BASE_URL', '')}/video/{file.filename}"}

@app.get("/video/{filename}")
async def serve_video(filename: str):
    local_path = STATIC_DIR / filename
    if local_path.exists():
        return Response(
            content=local_path.read_bytes(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f"inline; filename={filename}",
                "Content-Type": "video/mp4",
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600",
            }
        )
    video_url = f"https://emili-streamlit.onrender.com/app/static/{filename}"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(video_url)
            if resp.status_code != 200:
                raise HTTPException(status_code=404, detail=f"Video not found: {filename}")
            return Response(
                content=resp.content,
                media_type="video/mp4",
                headers={
                    "Content-Disposition": f"inline; filename={filename}",
                    "Content-Type": "video/mp4",
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "public, max-age=3600",
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/terms", response_class=HTMLResponse)
def terms():
    p = Path("legal/terms.html")
    if p.exists():
        return HTMLResponse(p.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>Terms of Service</h2><p>Contact hind@emili.net</p>")

@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    p = Path("legal/privacy.html")
    if p.exists():
        return HTMLResponse(p.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>Privacy Policy</h2><p>Contact hind@emili.net</p>")

@app.get("/delete-data", response_class=HTMLResponse)
def delete_data():
    p = Path("legal/delete-data.html")
    if p.exists():
        return HTMLResponse(p.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>Data Deletion</h2><p>Contact hind@emili.net</p>")

@app.get("/terms/tiktokbMAqnZ7SmHY8UcJAC3WSKhv9FtDrJSTV.txt")
def verify_tiktok_terms_new():
    return Response(
        content="tiktok-developers-site-verification=bMAqnZ7SmHY8UcJAC3WSKhv9FtDrJSTV",
        media_type="text/plain"
    )

@app.get("/tiktokbMAqnZ7SmHY8UcJAC3WSKhv9FtDrJSTV.txt")
def verify_tiktok_root_new():
    return Response(
        content="tiktok-developers-site-verification=bMAqnZ7SmHY8UcJAC3WSKhv9FtDrJSTV",
        media_type="text/plain"
    )

@app.get("/auth/tiktok/start")
def tiktok_auth_start():
    if not TIKTOK_CLIENT_KEY or not TIKTOK_REDIRECT_URI:
        return HTMLResponse("<h1>Server Error</h1><p>Missing config in Render.</p>", status_code=500)

    params = {
        "client_key": TIKTOK_CLIENT_KEY,
        "response_type": "code",
        "scope": "video.upload",
        "redirect_uri": TIKTOK_REDIRECT_URI,
        "state": "emili_secure_state_123"
    }

    url = f"{TIKTOK_AUTH_URL}?{urllib.parse.urlencode(params)}"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Connect TikTok - Emili</title></head>
<body style="display:flex;justify-content:center;align-items:center;height:100vh;font-family:Arial,sans-serif;background:#f9fafb;margin:0;">
  <div style="text-align:center;padding:40px;background:white;border-radius:10px;border:1px solid #eee;max-width:400px;">
    <h2 style="color:#111;margin-bottom:12px;">Connect TikTok</h2>
    <p style="color:#666;margin-bottom:24px;font-size:15px;">Authorize Emili to publish adoption videos to your TikTok account.</p>
    <a href="{url}" style="display:inline-block;padding:14px 28px;background:#fe2c55;color:#fff;text-decoration:none;font-size:16px;font-weight:600;border-radius:8px;">
      Login with TikTok
    </a>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html_content)

@app.get("/auth/tiktok/callback")
def tiktok_auth_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None
):
    if error:
        return HTMLResponse(f"<h1>TikTok Auth Error</h1><p>{error}: {error_description}</p>")
    if not code:
        return HTMLResponse("<h1>TikTok Callback</h1><p>No code received.</p>")
    if not TIKTOK_CLIENT_KEY or not TIKTOK_CLIENT_SECRET or not TIKTOK_REDIRECT_URI:
        return HTMLResponse("<h1>Server Config Error</h1><p>Missing API Keys.</p>")

    data = {
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": TIKTOK_REDIRECT_URI,
    }

    try:
        token_res = requests.post(
            TIKTOK_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"},
            timeout=30,
        )
        token_data = token_res.json()

        if "access_token" in token_data:
            TOKENS["tiktok"] = token_data
            save_tokens(TOKENS)
            access_token = token_data.get("access_token", "")
            refresh_token = token_data.get("refresh_token", "")
            return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>TikTok Connected - Emili</title></head>
<body style="font-family:Arial,sans-serif;padding:40px;background:#f0fdf4;max-width:600px;margin:0 auto;">
  <h1 style="color:#166534;margin-bottom:16px;">TikTok connected</h1>
  <p style="margin-bottom:20px;">Add both values to your Render environment variables and your local .env file.</p>
  <p><strong>TIKTOK_ACCESS_TOKEN</strong></p>
  <textarea style="width:100%;height:60px;font-family:monospace;font-size:12px;margin-bottom:16px;">{access_token}</textarea>
  <p><strong>TIKTOK_REFRESH_TOKEN</strong></p>
  <textarea style="width:100%;height:60px;font-family:monospace;font-size:12px;">{refresh_token}</textarea>
</body>
</html>""")
        else:
            return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>TikTok Error - Emili</title></head>
<body style="font-family:Arial,sans-serif;padding:40px;background:#fff7ed;">
  <h1 style="color:#b91c1c;">TikTok token exchange failed</h1>
  <pre>{json.dumps(token_data, indent=2)}</pre>
</body>
</html>""")
    except Exception as e:
        return HTMLResponse(f"<h1>Internal Server Error</h1><p>{str(e)}</p>")

@app.get("/auth/tiktok/status")
def tiktok_status():
    tiktok_data = TOKENS.get("tiktok")
    if not tiktok_data:
        return {"tiktok_connected": False, "access_token": None}
    access_token = tiktok_data.get("access_token") or tiktok_data.get("data", {}).get("access_token")
    return {"tiktok_connected": bool(access_token), "access_token": access_token}

@app.get("/auth/meta/start")
def meta_auth_start():
    if not META_APP_ID or not META_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="Missing META_APP_ID or META_REDIRECT_URI.")

    scopes = os.getenv("META_SCOPES", "public_profile,email,pages_show_list,pages_read_engagement,instagram_basic,instagram_content_publish")
    state = secrets.token_urlsafe(16)
    OAUTH_STATE_META[state] = True

    params = {
        "client_id": META_APP_ID,
        "redirect_uri": META_REDIRECT_URI,
        "state": state,
        "response_type": "code",
        "scope": scopes,
    }

    url = requests.Request("GET", META_AUTH_URL, params=params).prepare().url
    return RedirectResponse(url)

@app.get("/auth/meta/callback")
def meta_auth_callback(code: Optional[str] = None, state: Optional[str] = None):
    if not code:
        return JSONResponse({"error": "Missing code"}, status_code=400)
    if not META_APP_ID or not META_APP_SECRET or not META_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="Missing Meta credentials.")

    params = {
        "client_id": META_APP_ID,
        "client_secret": META_APP_SECRET,
        "redirect_uri": META_REDIRECT_URI,
        "code": code,
    }

    token_res = requests.get(META_TOKEN_URL, params=params, timeout=30)
    data = token_res.json()

    if "access_token" in data:
        try:
            ll_res = requests.get(
                "https://graph.facebook.com/v19.0/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": META_APP_ID,
                    "client_secret": META_APP_SECRET,
                    "fb_exchange_token": data["access_token"],
                },
                timeout=30,
            )
            ll_data = ll_res.json()
            if "access_token" in ll_data:
                data = ll_data
        except Exception as e:
            print(f"Long-lived token exchange failed: {e}")

        TOKENS["meta"] = data
        save_tokens(TOKENS)
        return HTMLResponse("<h1>Meta connected</h1><p>Long-lived token saved. You can close this window.</p>")
    else:
        return JSONResponse({"error": "Failed to get token", "details": data}, status_code=400)

@app.get("/auth/meta/status")
def meta_status():
    return {"meta_token_present": TOKENS.get("meta") is not None, "meta_token": TOKENS.get("meta")}

@app.get("/auth/meta/find-my-ids")
def find_my_ids():
    access_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
    if not access_token:
        meta_data = TOKENS.get("meta")
        if not meta_data or "access_token" not in meta_data:
            return JSONResponse({"error": "Token not found. Go to /auth/meta/start first."}, status_code=400)
        access_token = meta_data["access_token"]

    url = "https://graph.facebook.com/v19.0/me/accounts"
    params = {"access_token": access_token, "fields": "name,id,access_token,instagram_business_account"}
    try:
        r = requests.get(url, params=params)
        return {"MESSAGE": "Copy these values to Render environment", "DATA": r.json()}
    except Exception as e:
        return {"error": str(e)}

class GenRequest(BaseModel):
    pet_dir: str
    logo_path: Optional[str] = "assets/branding/logo.jpg"
    music_dir: Optional[str] = "assets/music"
    tone: str = "auto"
    fps: int = 30
    target_duration: int = 20
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
    if not out_path.is_absolute():
        out_path = OUT_DIR / out_path.name
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
    if not video_path.is_absolute():
        video_path = OUT_DIR / video_path.name
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

@app.get("/debug/out")
def debug_out():
    return {"files": [p.name for p in OUT_DIR.glob("*")]}

@app.get("/{filename}.txt")
def serve_txt(filename: str):
    file_path = STATIC_DIR / f"{filename}.txt"
    if file_path.exists():
        return FileResponse(str(file_path), media_type="text/plain")
    raise HTTPException(status_code=404, detail="File not found")

async def _proxy_to_streamlit(request: Request) -> Response:
    path = request.url.path
    query = request.url.query
    target_url = f"{STREAMLIT_BASE}{path}"
    if query:
        target_url += f"?{query}"

    req_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "accept-encoding")
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            proxy_req = client.build_request(
                method=request.method,
                url=target_url,
                headers=req_headers,
                content=await request.body(),
            )
            proxy_resp = await client.send(proxy_req)
            resp_headers = dict(proxy_resp.headers)
            resp_headers.pop("content-encoding", None)
            resp_headers.pop("transfer-encoding", None)
            resp_headers.pop("content-length", None)
            return Response(
                content=proxy_resp.content,
                status_code=proxy_resp.status_code,
                headers=resp_headers,
            )
    except Exception:
        return HTMLResponse(
            "<h2>Emili App</h2><p>Starting up... please refresh in a few seconds.</p>",
            status_code=503,
        )

@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"]
)
async def proxy_streamlit(path: str, request: Request):
    return await _proxy_to_streamlit(request)

@app.websocket("/{path:path}")
async def websocket_proxy(websocket: WebSocket, path: str):
    await websocket.accept()
    query = websocket.url.query
    target_ws_url = f"wss://emili-streamlit.onrender.com/{path}"
    if query:
        target_ws_url += f"?{query}"

    try:
        async with websockets.connect(target_ws_url) as ws:
            async def client_to_server():
                try:
                    while True:
                        data = await websocket.receive()
                        if data.get("text") is not None:
                            await ws.send(data["text"])
                        elif data.get("bytes") is not None:
                            await ws.send(data["bytes"])
                except Exception:
                    pass

            async def server_to_client():
                try:
                    while True:
                        data = await ws.recv()
                        if isinstance(data, str):
                            await websocket.send_text(data)
                        else:
                            await websocket.send_bytes(data)
                except Exception:
                    pass

            await asyncio.gather(client_to_server(), server_to_client())
    except Exception as e:
        print(f"WebSocket proxy error: {e}")
        try:
            await websocket.close()
        except Exception:
            pass