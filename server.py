from __future__ import annotations

from fastapi.staticfiles import StaticFiles

import asyncio
import websockets
from fastapi import WebSocket

import os
import secrets
import json
import urllib.parse
from pathlib import Path
from typing import List, Optional, Dict, Any

import httpx
import requests
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import PetProjectConfig
from backend.generate import generate_video
from backend.social import post_to_platform

app = FastAPI(title="Emili Emotional Adoption Video Generator API")

STREAMLIT_BASE = "http://127.0.0.1:8501"


# ==========================================
# HEALTH
# ==========================================

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/debug/out")
def debug_out():
    return {
        "out_dir": str(OUT_DIR),
        "exists": OUT_DIR.exists(),
        "files": [p.name for p in OUT_DIR.glob("*")]
    }

# ==========================================
# LEGAL PAGES
# ==========================================

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


# ==========================================
# TIKTOK DOMAIN VERIFICATION
# ==========================================

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

@app.get("/{filename}.txt")
def serve_txt(filename: str):
    file_path = STATIC_DIR / f"{filename}.txt"
    if file_path.exists():
        return FileResponse(str(file_path), media_type="text/plain")
    raise HTTPException(status_code=404, detail="File not found")


# ==========================================
# STATIC FILE MOUNTS
# ==========================================

OUT_DIR = Path("out").resolve()
OUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/out", StaticFiles(directory=str(OUT_DIR)), name="out")

ASSETS_DIR = Path("assets")
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)

LEGAL_DIR = Path("legal")
if LEGAL_DIR.exists():
    app.mount("/legal", StaticFiles(directory="legal", html=True), name="legal")


# ==========================================
# TOKEN STORAGE
# ==========================================

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
        print(f"Erreur de sauvegarde des tokens: {e}")

TOKENS: Dict[str, Any] = load_tokens()


# ==========================================
# TIKTOK AUTH
# ==========================================

TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
TIKTOK_REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI")

TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

@app.get("/auth/tiktok/start")
def tiktok_auth_start():
    if not TIKTOK_CLIENT_KEY or not TIKTOK_REDIRECT_URI:
        return HTMLResponse("<h1>❌ Erreur Serveur</h1><p>Configuration manquante dans Render.</p>", status_code=500)

    params = {
        "client_key": TIKTOK_CLIENT_KEY,
        "response_type": "code",
        
        "scope": "user.info.basic,video.upload",
        "redirect_uri": TIKTOK_REDIRECT_URI,
        "state": "emili_secure_state_123"
    }

    url = f"{TIKTOK_AUTH_URL}?{urllib.parse.urlencode(params)}"

    html_content = f"""
    <html>
        <body style="display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;background:#f9fafb;margin:0;">
            <div style="text-align:center;padding:40px;background:white;border-radius:10px;box-shadow:0 4px 10px rgba(0,0,0,0.1);">
                <h2 style="color:#333;">Connexion à TikTok</h2>
                <p style="color:#666;">Cliquez ci-dessous pour autoriser l'application.</p>
                <a href="{url}" style="display:inline-block;padding:15px 30px;background:#fe2c55;color:#fff;text-decoration:none;font-size:18px;font-weight:bold;border-radius:8px;margin-top:20px;">
                    Se connecter à TikTok
                </a>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/auth/tiktok/callback")
def tiktok_auth_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None
):
    if error:
        return HTMLResponse(f"<h1>❌ TikTok Authorization Error</h1><p>{error}: {error_description}</p>")
    if not code:
        return HTMLResponse("<h1>TikTok OAuth Callback</h1><p>No authorization code received.</p>")
    if not TIKTOK_CLIENT_KEY or not TIKTOK_CLIENT_SECRET or not TIKTOK_REDIRECT_URI:
        return HTMLResponse("<h1>❌ Server Configuration Error</h1><p>Missing API Keys in Render.</p>")

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
            return HTMLResponse("""
            <html><body style="font-family:Arial,sans-serif;padding:40px;background:#f0fdf4;">
                <h1 style="color:#166534;">✅ TikTok Connected Successfully!</h1>
                <p>Le token a été sauvegardé. Vous pouvez fermer cette page et cliquer sur Publish.</p>
            </body></html>
            """)
        else:
            return HTMLResponse(f"""
            <html><body style="font-family:Arial,sans-serif;padding:40px;background:#fff7ed;">
                <h1 style="color:#b91c1c;">❌ TikTok Token Exchange Failed</h1>
                <pre>{json.dumps(token_data, indent=2)}</pre>
            </body></html>
            """)
    except Exception as e:
        return HTMLResponse(f"<h1>❌ Internal Server Error</h1><p>{str(e)}</p>")


# ==========================================
# META AUTH
# ==========================================

META_APP_ID = os.getenv("META_APP_ID") or os.getenv("FACEBOOK_APP_ID")
META_APP_SECRET = os.getenv("META_APP_SECRET") or os.getenv("FACEBOOK_APP_SECRET")
META_REDIRECT_URI = os.getenv("META_REDIRECT_URI") or os.getenv("FACEBOOK_REDIRECT_URI")

META_AUTH_URL = "https://www.facebook.com/v19.0/dialog/oauth"
META_TOKEN_URL = "https://graph.facebook.com/v19.0/oauth/access_token"
OAUTH_STATE_META: Dict[str, bool] = {}

@app.get("/auth/meta/start")
def meta_auth_start():
    if not META_APP_ID or not META_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="Missing META_APP_ID or META_REDIRECT_URI in environment.")

    scopes = os.getenv("META_SCOPES", "public_profile,email")
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
        return JSONResponse({"error": "Invalid OAuth response, missing code"}, status_code=400)
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

    if "access_token" in data:
        TOKENS["meta"] = data
        save_tokens(TOKENS)
        return HTMLResponse("<h1>✅ Compte Meta connecté avec succès!</h1><p>Vous pouvez fermer cette fenêtre.</p>")
    else:
        return JSONResponse({"error": "Failed to get token", "details": data}, status_code=400)

@app.get("/auth/meta/status")
def meta_status():
    return {"meta_token_present": TOKENS.get("meta") is not None, "meta_token": TOKENS.get("meta")}

@app.get("/auth/meta/find-my-ids")
def find_my_ids():
    meta_data = TOKENS.get("meta")
    if not meta_data or "access_token" not in meta_data:
        return JSONResponse({
            "error": "Token introuvable ou invalide!",
            "action": "Allez d'abord sur /auth/meta/start pour vous reconnecter.",
            "debug": meta_data
        }, status_code=400)

    user_token = meta_data["access_token"]
    url = "https://graph.facebook.com/v19.0/me/accounts"
    params = {"access_token": user_token, "fields": "name,id,access_token,instagram_business_account"}

    try:
        r = requests.get(url, params=params)
        return {"MESSAGE": "✅ Copiez ces valeurs dans Render > Environment", "DATA": r.json()}
    except Exception as e:
        return {"error": str(e)}


# ==========================================
# GENERATE & PUBLISH
# ==========================================

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


# ==========================================
# REVERSE PROXY → STREAMLIT (catch-all)
# ==========================================

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
            resp_headers.pop("content-length", None)
            return Response(
                content=proxy_resp.content,
                status_code=proxy_resp.status_code,
                headers=resp_headers,
            )
    except Exception:
        return HTMLResponse(
            "<h2>Emili App</h2><p>Démarrage en cours... veuillez rafraîchir la page dans quelques secondes.</p>",
            status_code=503,
        )

@app.get("/debug/out")
def debug_out():
    return {"files": [p.name for p in OUT_DIR.glob("*")]}

@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"]
)
async def proxy_streamlit(path: str, request: Request):
    """Proxy everything not matched above to Streamlit."""
    return await _proxy_to_streamlit(request)


# ==========================================
# WEBSOCKET PROXY → STREAMLIT
# ==========================================

@app.websocket("/{path:path}")
async def websocket_proxy(websocket: WebSocket, path: str):
    await websocket.accept()
    query = websocket.url.query
    target_ws_url = f"ws://127.0.0.1:8501/{path}"
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
        print(f"Erreur WebSocket Proxy: {e}")
        try:
            await websocket.close()
        except Exception:
            pass
