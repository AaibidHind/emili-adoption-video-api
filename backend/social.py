from __future__ import annotations

import json
import os
import time
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
    # Ensure JSON-serializable
    payload = asdict(res)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)


# =========================
# Public URL helper
# =========================
def _public_url_for_file(video_path: Path) -> Optional[str]:
    """
    IMPORTANT:
    Your FastAPI mounts: app.mount("/out", StaticFiles(directory="out"), name="out")
    So the public URL must include /out/<filename>.
    """
    base = os.getenv("SOCIAL_PUBLIC_BASE_URL")
    if not base:
        return None
    return f"{base.rstrip('/')}/out/{video_path.name}"


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
            # optionally log status.progress()

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
# Facebook Page video via file_url
# =========================
def _post_to_facebook_page_via_url(video_path: Path, title: str, description: str) -> SocialPostResult:
    page_id = os.getenv("FACEBOOK_PAGE_ID")
    access_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
    file_url = _public_url_for_file(video_path)

    if not page_id or not access_token:
        res = SocialPostResult("facebook", False, "Missing FACEBOOK_PAGE_ID or FACEBOOK_PAGE_ACCESS_TOKEN", str(video_path), title, description)
        _log_result(res)
        return res

    if not file_url:
        res = SocialPostResult("facebook", False, "Missing SOCIAL_PUBLIC_BASE_URL (public domain for /out/...)", str(video_path), title, description)
        _log_result(res)
        return res

    url = f"https://graph.facebook.com/v19.0/{page_id}/videos"
    data = {
        "access_token": access_token,
        "file_url": file_url,
        "description": description,
        "title": title,
    }

    try:
        r = requests.post(url, data=data, timeout=600)
        r.raise_for_status()
        j = r.json()
        res = SocialPostResult(
            "facebook",
            True,
            "Facebook upload completed.",
            str(video_path),
            title,
            description,
            {"video_id": j.get("id"), "file_url": file_url, "graph_response": j},
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
            {"file_url": file_url, "hint": "Check token permissions + page role + file_url reachable"},
        )
        _log_result(res)
        return res


# =========================
# Instagram (Reels/Video) via Container + Publish
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
        res = SocialPostResult("instagram", False, "Missing SOCIAL_PUBLIC_BASE_URL (public domain for /out/...)", str(video_path), title, description)
        _log_result(res)
        return res

    caption = f"{title}\n\n{description}".strip()

    graph_version = os.getenv("META_GRAPH_VERSION", "v19.0")
    media_type = os.getenv("INSTAGRAM_MEDIA_TYPE", "REELS")  # "REELS" or "VIDEO"

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
        res = SocialPostResult("instagram", False, f"Instagram create container failed: {repr(e)}", str(video_path), title, description, {"video_url": video_url})
        _log_result(res)
        return res

    # 2) Poll processing status
    status_url = f"https://graph.facebook.com/{graph_version}/{creation_id}"
    status_params = {"access_token": access_token, "fields": "status_code"}

    max_retries = int(os.getenv("INSTAGRAM_MAX_RETRIES", "30"))
    sleep_sec = int(os.getenv("INSTAGRAM_POLL_SECONDS", "5"))

    for _ in range(max_retries):
        try:
            s = requests.get(status_url, params=status_params, timeout=30)
            s.raise_for_status()
            data = s.json()
            code = data.get("status_code")  # FINISHED / IN_PROGRESS / ERROR

            if code == "FINISHED":
                break
            if code == "ERROR":
                res = SocialPostResult("instagram", False, f"Instagram processing error: {data}", str(video_path), title, description, {"creation_id": creation_id})
                _log_result(res)
                return res

            time.sleep(sleep_sec)
        except Exception:
            time.sleep(sleep_sec)
    else:
        res = SocialPostResult("instagram", False, "Instagram processing timed out", str(video_path), title, description, {"creation_id": creation_id})
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
        res = SocialPostResult(
            "instagram",
            False,
            f"Instagram publish failed: {err_text}",
            str(video_path),
            title,
            description,
            {"creation_id": creation_id, "video_url": video_url, "media_type": media_type},
        )
        _log_result(res)
        return res

    res = SocialPostResult(
        "instagram",
        True,
        "Instagram published successfully.",
        str(video_path),
        title,
        description,
        {"creation_id": creation_id, "instagram_post_id": publish_json.get("id"), "video_url": video_url, "media_type": media_type},
    )
    _log_result(res)
    return res


# =========================
# TikTok placeholder
# =========================
def _post_to_tiktok_stub(video_path: Path, title: str, description: str) -> SocialPostResult:
    res = SocialPostResult("tiktok", False, "TikTok auto-post not implemented yet.", str(video_path), title, description)
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
        res = _post_to_tiktok_stub(video_path, title, description)
    else:
        res = SocialPostResult(normalized, False, f"Platform '{platform}' unknown", str(video_path), title, description)
        _log_result(res)

    return asdict(res)
