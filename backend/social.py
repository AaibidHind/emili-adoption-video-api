from __future__ import annotations

import json
import os
import time
import urllib.parse
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# =========================
# Models / logging
# =========================
@dataclass
class SocialPostResult:
    platform: str
    success: bool
    message: str
    video_path: str
    title: str
    description: str
    extra: Optional[Dict[str, Any]] = None


LOG_DIR = Path("out/social_logs")


def _log_result(res: SocialPostResult) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_platform = res.platform.replace("/", "_").replace("\\", "_")
    out_path = LOG_DIR / f"{ts}_{safe_platform}.json"
    payload = asdict(res)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)


# =========================
# Public URL helper (CORRIGÉ POUR FASTAPI)
# =========================

def _public_url_for_file(video_path: Path) -> Optional[str]:
    base = os.getenv("SOCIAL_PUBLIC_BASE_URL")
    if not base:
        return None
    
    # On pointe directement vers le dossier /out/ géré par FastAPI
    # Plus besoin de copier les fichiers !
    safe_name = urllib.parse.quote(video_path.name)
    return f"{base.rstrip('/')}/out/{safe_name}"


# =========================
# YouTube
# =========================
def _build_youtube_client() -> Tuple[Optional[Any], Optional[str]]:
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")

    if not client_id or not client_secret or not refresh_token:
        return None, (
            "Missing YouTube OAuth credentials. "
            "Set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN."
        )

    token_uri = "https://oauth2.googleapis.com/token"
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]

    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
        )

        if not creds.valid:
            creds.refresh(Request())

        youtube = build("youtube", "v3", credentials=creds)
        return youtube, None
    except Exception as e:
        return None, f"Failed to build YouTube client: {repr(e)}"


def _upload_to_youtube(video_path: Path, title: str, description: str) -> SocialPostResult:
    youtube, err = _build_youtube_client()
    if youtube is None:
        res = SocialPostResult("youtube", False, err or "Could not build YouTube client.", str(video_path), title, description)
        _log_result(res)
        return res

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/*")

    body = {
        "snippet": {"title": title, "description": description, "categoryId": "22"},
        "status": {"privacyStatus": "unlisted"},  # or "public"
    }

    try:
        req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = req.next_chunk()

        video_id = response.get("id")
        extra = {
            "video_id": video_id,
            "watch_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
            "raw": response,
        }

        res = SocialPostResult("youtube", True, "YouTube upload completed.", str(video_path), title, description, extra)
        _log_result(res)
        return res
    except Exception as e:
        res = SocialPostResult("youtube", False, f"YouTube upload failed: {repr(e)}", str(video_path), title, description)
        _log_result(res)
        return res


# =========================
# Facebook Page video
# =========================
def _post_to_facebook_page_via_url(video_path: Path, title: str, description: str) -> SocialPostResult:
    page_id = os.getenv("FACEBOOK_PAGE_ID")
    access_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")

    if not page_id or not access_token:
        res = SocialPostResult("facebook", False, "Missing FACEBOOK_PAGE_ID or FACEBOOK_PAGE_ACCESS_TOKEN", str(video_path), title, description)
        _log_result(res)
        return res

    url = f"https://graph.facebook.com/v19.0/{page_id}/videos"
    
    data = {
        "access_token": access_token,
        "description": description,
        "title": title,
    }

    try:
        with open(video_path, "rb") as video_file:
            files = {
                "source": video_file
            }
            r = requests.post(url, data=data, files=files, timeout=600)
            
        r.raise_for_status()
        j = r.json()
        res = SocialPostResult(
            "facebook",
            True,
            "Facebook direct upload completed.",
            str(video_path),
            title,
            description,
            {"video_id": j.get("id"), "graph_response": j},
        )
        _log_result(res)
        return res
    except requests.RequestException as e:
        err_text = ""
        if getattr(e, "response", None) is not None:
            err_text = e.response.text
        res = SocialPostResult(
            "facebook",
            False,
            f"Facebook upload failed: {err_text or repr(e)}",
            str(video_path),
            title,
            description,
            {"hint": "Check token permissions + page role"},
        )
        _log_result(res)
        return res

# =========================
# Instagram
# =========================
def _post_to_instagram_via_url(video_path: Path, title: str, description: str) -> SocialPostResult:
    ig_user_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    access_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or os.getenv("INSTAGRAM_ACCESS_TOKEN")
    video_url = _public_url_for_file(video_path)

    if not ig_user_id or not access_token:
        res = SocialPostResult("instagram", False, "Missing INSTAGRAM_BUSINESS_ACCOUNT_ID or access token", str(video_path), title, description)
        _log_result(res)
        return res

    if not video_url:
        res = SocialPostResult("instagram", False, "Missing SOCIAL_PUBLIC_BASE_URL", str(video_path), title, description)
        _log_result(res)
        return res

    caption = f"{title}\n\n{description}".strip()
    graph_version = os.getenv("META_GRAPH_VERSION", "v19.0")
    media_type = os.getenv("INSTAGRAM_MEDIA_TYPE", "REELS")

    # 1) Create container
    create_url = f"https://graph.facebook.com/{graph_version}/{ig_user_id}/media"
    create_data = {
        "media_type": media_type,
        "video_url": video_url,
        "caption": caption,
        "access_token": access_token,
    }

    try:
        create_resp = requests.post(create_url, data=create_data, timeout=600)
        create_resp.raise_for_status()
        creation_id = create_resp.json().get("id")
        if not creation_id:
            raise RuntimeError(f"No creation_id returned. Response: {create_resp.text}")
    except Exception as e:
        err_txt = repr(e)
        if hasattr(e, "response") and e.response is not None:
            err_txt = e.response.text
        res = SocialPostResult("instagram", False, f"Instagram create container failed: {err_txt}", str(video_path), title, description, {"video_url": video_url})
        _log_result(res)
        return res

    # 2) Poll processing status
    status_url = f"https://graph.facebook.com/{graph_version}/{creation_id}"
    status_params = {"access_token": access_token, "fields": "status_code,status"}
    
    max_retries = int(os.getenv("INSTAGRAM_MAX_RETRIES", "60"))
    sleep_sec = int(os.getenv("INSTAGRAM_POLL_SECONDS", "5"))

    last_error_log = None

    for attempt in range(max_retries):
        try:
            s = requests.get(status_url, params=status_params, timeout=30)
            if s.status_code != 200:
                last_error_log = f"HTTP {s.status_code}: {s.text}"
            
            s.raise_for_status()
            data = s.json()
            code = data.get("status_code")

            if code == "FINISHED":
                break
            if code == "ERROR":
                raw_status = data.get("status", "Raison inconnue")
                if isinstance(raw_status, dict):
                    error_msg = raw_status.get("error_message", str(raw_status))
                else:
                    error_msg = str(raw_status)
                
                res = SocialPostResult("instagram", False, f"Instagram a rejeté la vidéo : {error_msg}", str(video_path), title, description, {"creation_id": creation_id, "video_url": video_url})
                _log_result(res)
                return res

            time.sleep(sleep_sec)
        except Exception as e:
            last_error_log = str(e)
            time.sleep(sleep_sec)
    else:
        error_msg = f"Instagram processing timed out. Dernière erreur: {last_error_log}"
        res = SocialPostResult("instagram", False, error_msg, str(video_path), title, description, {"creation_id": creation_id, "video_url": video_url})
        _log_result(res)
        return res

    # 3) Publish
    publish_url = f"https://graph.facebook.com/{graph_version}/{ig_user_id}/media_publish"
    publish_data = {"creation_id": creation_id, "access_token": access_token}

    try:
        publish_resp = requests.post(publish_url, data=publish_data, timeout=600)
        publish_resp.raise_for_status()
        publish_json = publish_resp.json()
    except requests.RequestException as e:
        err_text = e.response.text if getattr(e, "response", None) is not None else repr(e)
        res = SocialPostResult("instagram", False, f"Instagram publish failed: {err_text}", str(video_path), title, description, {"creation_id": creation_id})
        _log_result(res)
        return res

    res = SocialPostResult("instagram", True, "Instagram published successfully.", str(video_path), title, description, {"instagram_post_id": publish_json.get("id")})
    _log_result(res)
    return res

# =========================
# TikTok
# =========================
def _post_to_tiktok_via_url(video_path: Path, title: str, description: str) -> SocialPostResult:
    # 1. Récupération du token
    token_file = Path("tokens.json")
    access_token = None
    if token_file.exists():
        try:
            tokens = json.loads(token_file.read_text(encoding="utf-8"))
            tk_data = tokens.get("tiktok", {})
            access_token = tk_data.get("access_token") or tk_data.get("data", {}).get("access_token")
        except Exception:
            pass
            
    if not access_token:
        res = SocialPostResult("tiktok", False, "Missing TikTok access token. Allez sur /auth/tiktok/start d'abord.", str(video_path), title, description)
        _log_result(res)
        return res

    # 2. Lien public généré (CORRIGÉ)
    video_url = _public_url_for_file(video_path)
    if not video_url:
        res = SocialPostResult("tiktok", False, "Missing SOCIAL_PUBLIC_BASE_URL", str(video_path), title, description)
        _log_result(res)
        return res

    # 3. Requête API
    url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8"
    }
    
    full_title = f"{title}\n\n{description}"
    full_title = full_title[:2000] # Limite de sécurité

    privacy_level = os.getenv("TIKTOK_PRIVACY_LEVEL", "SELF_ONLY")

    payload = {
        "post_info": {
            "title": full_title,
            "privacy_level": privacy_level,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 1000
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "video_url": video_url
        }
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        data = r.json()
        
        if "error" in data and data["error"].get("code") != "ok":
            error_msg = data["error"].get("message", "Erreur inconnue")
            res = SocialPostResult("tiktok", False, f"TikTok a rejeté la vidéo: {error_msg} (Détails: {data})", str(video_path), title, description, {"raw": data})
            _log_result(res)
            return res
            
        publish_id = data.get("data", {}).get("publish_id")
        
        res = SocialPostResult(
            "tiktok", 
            True, 
            "TikTok publish initialized successfully.", 
            str(video_path), 
            title, 
            description, 
            {"publish_id": publish_id, "video_url": video_url, "privacy": privacy_level}
        )
        _log_result(res)
        return res
        
    except Exception as e:
        err_text = str(e)
        if hasattr(e, "response") and e.response is not None:
            err_text = e.response.text
            
        res = SocialPostResult("tiktok", False, f"TikTok API error: {err_text}", str(video_path), title, description)
        _log_result(res)
        return res


# =========================
# Public entry point
# =========================
def post_to_platform(platform: str, video_path: Path, title: str, description: str) -> Dict[str, Any]:
    normalized = platform.lower().strip()

    if normalized == "youtube":
        res = _upload_to_youtube(video_path, title, description)
    elif normalized == "facebook":
        res = _post_to_facebook_page_via_url(video_path, title, description)
    elif normalized == "instagram":
        res = _post_to_instagram_via_url(video_path, title, description)
    elif normalized == "tiktok":
        res = _post_to_tiktok_via_url(video_path, title, description)
    else:
        res = SocialPostResult(normalized, False, f"Platform '{platform}' unknown", str(video_path), title, description)
        _log_result(res)

    return asdict(res)
