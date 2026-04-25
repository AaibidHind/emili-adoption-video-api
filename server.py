from __future__ import annotations

import asyncio
import os
import secrets
import json
import urllib.parse
from pathlib import Path
from typing import List, Optional, Dict, Any

import httpx
import requests
import websockets
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import PetProjectConfig
from backend.generate import generate_video
from backend.social import post_to_platform

app = FastAPI(title="Emili Emotional Adoption Video Generator API")

# Streamlit runs internally on 8501, FastAPI is the public-facing server
STREAMLIT_BASE = "http://127.0.0.1:8501"

# These prefixes are handled by FastAPI — everything else proxies to Streamlit
FASTAPI_PREFIXES = (
    "/terms",
    "/privacy",
    "/delete-data",
    "/legal",
    "/assets",
    "/out",
    "/health",
    "/docs",
    "/openapi",
    "/auth",
    "/generate",
    "/publish",
)


# ==========================================
# HEALTH
# ==========================================

@app.get("/health")
def health():
    return {"status": "ok"}


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


# ==========================================
# EXPORT VIDEO & STATIC FILES (CORRIGÉ)
# ==========================================

# 1. Route ultra-robuste pour servir les vidéos à Meta/Instagram
@app.get("/out/{filename:path}")
@app.head("/out/{filename:path}")  # Meta utilise souvent HEAD avant de télécharger
def serve_out_file(filename: str):
    # On vérifie toutes les racines possibles sur Render
    paths_to_check = [
        Path(f"/opt/render/project/src/out/{filename}"),
        Path(f"out/{filename}").resolve(),
        Path.cwd() / "out" / filename
    ]
    
    for p in paths_to_check:
        if p.exists() and p.is_file():
            # FileResponse gère parfaitement le streaming et les requêtes Meta
            return FileResponse(
                str(p),
                media_type="video/mp4" if filename.endswith(".mp4") else "application/octet-stream",
                headers={"Accept-Ranges": "bytes", "Content-Disposition": "inline"}
            )
            
    raise HTTPException(status_code=404, detail=f"File not found: {filename}")

# 2. On garde les autres dossiers statiques
ASSETS_DIR = Path("assets")
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)

@app.get("/{filename}.txt")
def serve_txt(filename: str):
    file_path = STATIC_DIR / f"{filename}.txt"
    if file_path.exists():
        return FileResponse(str(file_path), media_type="text/plain")
    raise HTTPException(status_code=404, detail="File not found")

LEGAL_DIR = Path("legal")
if LEGAL_DIR.exists():
    app.mount("/legal", StaticFiles(directory="legal", html=True), name="legal")


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

@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"]
)
async def proxy_streamlit(path: str, request: Request):
    """Proxy everything not matched above to Streamlit."""
    full_path = "/" + path
    for prefix in FASTAPI_PREFIXES:
        if full_path.startswith(prefix):
            raise HTTPException(status_code=404, detail="Not found")
    return await _proxy_to_streamlit(request)


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
        "scope": "user.info.basic
