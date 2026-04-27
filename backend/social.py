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

import shutil


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
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(asdict(res), f, ensure_ascii=False, indent=2, default=str)


def _public_url_for_file(video_path: Path) -> Optional[str]:
    base = os.getenv("SOCIAL_PUBLIC_BASE_URL")
    if not base:
        return None
    safe_name = urllib.parse.quote(video_path.name)
    return f"{base.rstrip('/')}/app/static/{safe_name}"


def _build_youtube_client() -> Tuple[Optional[Any], Optional[str]]:
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
    if not client_id or not client_secret or not refresh_token:
        return None, "Missing YouTube OAuth credentials."
    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
        )
        if not creds.valid:
            creds.refresh(Request())
        return build("youtube", "v3", credentials=creds), None
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
        "status": {"privacyStatus": "unlisted"},
    }
    try:
        req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status, response = req.next_chunk()
        video_id = response.get("id")
        res = SocialPostResult("youtube", True, "YouTube upload completed.", str(video_path), title, description, {
            "video_id": video_id,
            "watch_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
        })
        _log_result(res)
        return res
    except Exception as e:
        res = SocialPostResult("youtube", False, f"YouTube upload failed: {repr(e)}", str(video_path), title, description)
        _log_result(res)
        return res


def _post_to_facebook_page_via_url(video_path: Path, title: str, description: str) -> SocialPostResult:
    page_id = os.getenv("FACEBOOK_PAGE_ID")
    access_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
    if not page_id or not access_token:
        res = SocialPostResult("facebook", False, "Missing FACEBOOK_PAGE_ID or FACEBOOK_PAGE_ACCESS_TOKEN", str(video_path), title, description)
        _log_result(res)
        return res
    try:
        with open(video_path, "rb") as video_file:
            r = requests.post(
                f"https://graph.facebook.com/v19.0/{page_id}/videos",
                data={"access_token": access_token, "description": description, "title": title},
                files={"source": video_file},
                timeout=600
            )
        r.raise_for_status()
        j = r.json()
        res = SocialPostResult("facebook", True, "Facebook direct upload completed.", str(video_path), title, description, {"video_id": j.get("id")})
        _log_result(res)
        return res
    except requests.RequestException as e:
        err_text = e.response.text if getattr(e, "response", None) is not None else repr(e)
        res = SocialPostResult("facebook", False, f"Facebook upload failed: {err_text}", str(video_path), title, description)
        _log_result(res)
        return res


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
    graph_version = os.getenv("META_GRAPH_VERSION", "v19.0")
    media_type = os.getenv("INSTAGRAM_MEDIA_TYPE", "REELS")
    caption = f"{title}\n\n{description}".strip()
    try:
        create_resp = requests.post(
            f"https://graph.facebook.com/{graph_version}/{ig_user_id}/media",
            data={"media_type": media_type, "video_url": video_url, "caption": caption, "access_token": access_token},
            timeout=600
        )
        create_resp.raise_for_status()
        creation_id = create_resp.json().get("id")
        if not creation_id:
            raise RuntimeError(f"No creation_id returned. Response: {create_resp.text}")
    except Exception as e:
        err_txt = e.response.text if hasattr(e, "response") and e.response is not None else repr(e)
        res = SocialPostResult("instagram", False, f"Instagram create container failed: {err_txt}", str(video_path), title, description)
        _log_result(res)
        return res
    max_retries = int(os.getenv("INSTAGRAM_MAX_RETRIES", "60"))
    sleep_sec = int(os.getenv("INSTAGRAM_POLL_SECONDS", "5"))
    last_error_log = None
    for _ in range(max_retries):
        try:
            s = requests.get(
                f"https://graph.facebook.com/{graph_version}/{creation_id}",
                params={"access_token": access_token, "fields": "status_code,status"},
                timeout=30
            )
            s.raise_for_status()
            data = s.json()
            code = data.get("status_code")
            if code == "FINISHED":
                break
            if code == "ERROR":
                raw_status = data.get("status", "Raison inconnue")
                error_msg = raw_status.get("error_message", str(raw_status)) if isinstance(raw_status, dict) else str(raw_status)
                res = SocialPostResult("instagram", False, f"Instagram a rejeté la vidéo : {error_msg}", str(video_path), title, description)
                _log_result(res)
                return res
            time.sleep(sleep_sec)
        except Exception as e:
            last_error_log = str(e)
            time.sleep(sleep_sec)
    else:
        res = SocialPostResult("instagram", False, f"Instagram processing timed out. Last error: {last_error_log}", str(video_path), title, description)
        _log_result(res)
        return res
    try:
        publish_resp = requests.post(
            f"https://graph.facebook.com/{graph_version}/{ig_user_id}/media_publish",
            data={"creation_id": creation_id, "access_token": access_token},
            timeout=600
        )
        publish_resp.raise_for_status()
        publish_json = publish_resp.json()
    except requests.RequestException as e:
        err_text = e.response.text if getattr(e, "response", None) is not None else repr(e)
        res = SocialPostResult("instagram", False, f"Instagram publish failed: {err_text}", str(video_path), title, description)
        _log_result(res)
        return res
    res = SocialPostResult("instagram", True, "Instagram published successfully.", str(video_path), title, description, {"instagram_post_id": publish_json.get("id")})
    _log_result(res)
    return res


def _get_tiktok_access_token() -> Optional[str]:
    token = os.getenv("TIKTOK_ACCESS_TOKEN")
    if token:
        return token
    token_file = Path("tokens.json")
    if token_file.exists():
        try:
            tokens = json.loads(token_file.read_text(encoding="utf-8"))
            tk_data = tokens.get("tiktok", {})
            return tk_data.get("access_token") or tk_data.get("data", {}).get("access_token")
        except Exception:
            pass
    return None


def _post_to_tiktok_via_url(video_path: Path, title: str, description: str) -> SocialPostResult:
    access_token = _get_tiktok_access_token()
    if not access_token:
        res = SocialPostResult("tiktok", False, "Missing TikTok access token. Go to /auth/tiktok/start first.", str(video_path), title, description)
        _log_result(res)
        return res

    full_title = f"{title}\n\n{description}"[:2200]
    privacy_level = os.getenv("TIKTOK_PRIVACY_LEVEL", "SELF_ONLY")
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=UTF-8"}

    video_size = video_path.stat().st_size
    FIVE_MB = 5 * 1024 * 1024
    if video_size <= FIVE_MB:
        chunk_size = video_size
        total_chunk_count = 1
    else:
        chunk_size = FIVE_MB
        total_chunk_count = -(-video_size // FIVE_MB)

    init_payload = {
        "post_info": {
            "title": full_title,
            "privacy_level": privacy_level,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 1000
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunk_count
        }
    }

    try:
        init_resp = requests.post(
            "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
            headers=headers, json=init_payload, timeout=30
        )
        init_data = init_resp.json()
        if "error" in init_data and init_data["error"].get("code") != "ok":
            res = SocialPostResult("tiktok", False, f"TikTok init failed: {init_data['error'].get('message', 'Unknown')}", str(video_path), title, description, {"raw": init_data})
            _log_result(res)
            return res
        publish_id = init_data.get("data", {}).get("publish_id")
        upload_url = init_data.get("data", {}).get("upload_url")
        if not publish_id or not upload_url:
            res = SocialPostResult("tiktok", False, f"No publish_id or upload_url: {init_data}", str(video_path), title, description)
            _log_result(res)
            return res
    except Exception as e:
        res = SocialPostResult("tiktok", False, f"TikTok init error: {str(e)}", str(video_path), title, description)
        _log_result(res)
        return res

    try:
        with open(video_path, "rb") as f:
            bytes_uploaded = 0
            while True:
                chunk_data = f.read(chunk_size)
                if not chunk_data:
                    break
                start_byte = bytes_uploaded
                end_byte = bytes_uploaded + len(chunk_data) - 1
                upload_resp = requests.put(
                    upload_url,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Range": f"bytes {start_byte}-{end_byte}/{video_size}",
                        "Content-Length": str(len(chunk_data))
                    },
                    data=chunk_data,
                    timeout=300
                )
                if upload_resp.status_code not in (200, 201, 206):
                    res = SocialPostResult("tiktok", False, f"Chunk upload failed: {upload_resp.status_code} {upload_resp.text}", str(video_path), title, description)
                    _log_result(res)
                    return res
                bytes_uploaded += len(chunk_data)
    except Exception as e:
        res = SocialPostResult("tiktok", False, f"TikTok upload error: {str(e)}", str(video_path), title, description)
        _log_result(res)
        return res

    res = SocialPostResult("tiktok", True, "TikTok video uploaded successfully as draft to inbox!", str(video_path), title, description, {"publish_id": publish_id, "privacy": privacy_level})
    _log_result(res)
    return res


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
