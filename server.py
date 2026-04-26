from __future__ import annotations

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
# DIRECTORIES
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
# HEALTH + DEBUG
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
# LEGAL
# ==========================================

@app.get("/terms", response_class=HTMLResponse)
def terms():
    p = Path("legal/terms.html")
    if p.exists():
        return HTMLResponse(p.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>Terms of Service</h2>")

@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    p = Path("legal/privacy.html")
    if p.exists():
        return HTMLResponse(p.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>Privacy Policy</h2>")

@app.get("/delete-data", response_class=HTMLResponse)
def delete_data():
    p = Path("legal/delete-data.html")
    if p.exists():
        return HTMLResponse(p.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>Delete Data</h2>")

# ==========================================
# GENERATE / PUBLISH
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
        "outfile": str(result.outfile) if result.outfile else None
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

    full_description = req.description
    if hashtags:
        full_description += "\n\n" + " ".join(f"#{h}" for h in hashtags)

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
# PROXY STREAMLIT (TOUT À LA FIN)
# ==========================================

FASTAPI_PREFIXES = (
    "/terms",
    "/privacy",
    "/delete-data",
    "/assets",
    "/out",
    "/health",
    "/debug",
    "/docs",
    "/openapi",
    "/auth",
    "/generate",
    "/publish",
)

async def _proxy_to_streamlit(request: Request) -> Response:
    target_url = f"{STREAMLIT_BASE}{request.url.path}"

    async with httpx.AsyncClient(timeout=30) as client:
        proxy_req = client.build_request(
            method=request.method,
            url=target_url,
            headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
            content=await request.body(),
        )
        proxy_resp = await client.send(proxy_req)

        return Response(
            content=proxy_resp.content,
            status_code=proxy_resp.status_code,
            headers=dict(proxy_resp.headers),
        )

@app.api_route("/{path:path}", methods=["GET","POST","PUT","DELETE","OPTIONS","HEAD","PATCH"])
async def proxy_streamlit(path: str, request: Request):
    full_path = "/" + path

    for prefix in FASTAPI_PREFIXES:
        if full_path.startswith(prefix):
            raise HTTPException(status_code=404, detail="Not found")

    return await _proxy_to_streamlit(request)

# ==========================================
# WEBSOCKET
# ==========================================

@app.websocket("/{path:path}")
async def websocket_proxy(websocket: WebSocket, path: str):
    await websocket.accept()

    target_ws_url = f"ws://127.0.0.1:8501/{path}"

    try:
        async with websockets.connect(target_ws_url) as ws:

            async def client_to_server():
                while True:
                    data = await websocket.receive_text()
                    await ws.send(data)

            async def server_to_client():
                while True:
                    data = await ws.recv()
                    await websocket.send_text(data)

            await asyncio.gather(client_to_server(), server_to_client())

    except Exception:
        await websocket.close()
