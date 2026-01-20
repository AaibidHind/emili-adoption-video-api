

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials



@dataclass
class SocialPostResult:
    platform: str
    success: bool
    message: str
    video_path: str
    title: str
    description: str
    extra: Dict[str, Any] | None = None


LOG_DIR = Path("out/social_logs")


def _log_result(res: SocialPostResult) -> None:

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    safe_platform = res.platform.replace("/", "_").replace("\\", "_")

    out_path = LOG_DIR / f"{ts}_{safe_platform}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(asdict(res), f, ensure_ascii=False, indent=2)



def _public_url_for_file(video_path: Path) -> Optional[str]:
    
    base = os.getenv("SOCIAL_PUBLIC_BASE_URL")
    if not base:
        return None

    return f"{base.rstrip('/')}/{video_path.name}"



def _build_youtube_client() -> Tuple[Any | None, str | None]:
   
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")

    if not client_id or not client_secret or not refresh_token:
        return None, (
            "Missing YouTube OAuth credentials. "
            "Set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and "
            "YOUTUBE_REFRESH_TOKEN in .env to enable YouTube uploads."
        )

    token_uri = "https://oauth2.googleapis.com/token"
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]

    try:
        creds = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
        )

        if not creds.valid:
            request = Request()
            creds.refresh(request)

        youtube = build("youtube", "v3", credentials=creds)
        return youtube, None
    except Exception as e:
        return None, f"Failed to build YouTube client: {repr(e)}"


def _upload_to_youtube(
    video_path: Path,
    title: str,
    description: str,
) -> SocialPostResult:
    
    youtube, err = _build_youtube_client()
    if youtube is None:
        msg = err or "Could not build YouTube client."
        res = SocialPostResult(
            platform="youtube",
            success=False,
            message=msg,
            video_path=str(video_path),
            title=title,
            description=description,
            extra=None,
        )
        _log_result(res)
        return res

    media = MediaFileUpload(
        filename=str(video_path),
        chunksize=-1,
        resumable=True,
        mimetype="video/*",
    )

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "22",  
        },
        "status": {
            "privacyStatus": "unlisted",
        },
    }

    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
        

        video_id = response.get("id")
        channel_id = response.get("snippet", {}).get("channelId")

        extra = {
            "video_id": video_id,
            "channel_id": channel_id,
            "watch_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
        }

        res = SocialPostResult(
            platform="youtube",
            success=True,
            message="YouTube upload completed.",
            video_path=str(video_path),
            title=title,
            description=description,
            extra=extra,
        )
        _log_result(res)
        return res

    except Exception as e:
        msg = f"YouTube upload failed: {repr(e)}"
        res = SocialPostResult(
            platform="youtube",
            success=False,
            message=msg,
            video_path=str(video_path),
            title=title,
            description=description,
            extra=None,
        )
        _log_result(res)
        return res



def _post_to_facebook_page_via_url(
    video_path: Path,
    title: str,
    description: str,
) -> SocialPostResult:
    
    page_id = os.getenv("FACEBOOK_PAGE_ID")
    access_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
    file_url = _public_url_for_file(video_path)

    if not page_id or not access_token:
        msg = (
            "Missing Facebook Page credentials. Set FACEBOOK_PAGE_ID and "
            "FACEBOOK_PAGE_ACCESS_TOKEN in .env to enable Facebook uploads."
        )
        res = SocialPostResult(
            platform="facebook",
            success=False,
            message=msg,
            video_path=str(video_path),
            title=title,
            description=description,
            extra=None,
        )
        _log_result(res)
        return res

    if not file_url:
        msg = (
            "SOCIAL_PUBLIC_BASE_URL is not set, so I cannot build a public "
            "file URL for the video. Configure SOCIAL_PUBLIC_BASE_URL in .env."
        )
        res = SocialPostResult(
            platform="facebook",
            success=False,
            message=msg,
            video_path=str(video_path),
            title=title,
            description=description,
            extra={"hint": "Need SOCIAL_PUBLIC_BASE_URL"},
        )
        _log_result(res)
        return res

    url = f"https://graph.facebook.com/v18.0/{page_id}/videos"

    data = {
        "access_token": access_token,
        "file_url": file_url,
        "description": description,
        "title": title,
    }

    try:
        response = requests.post(url, data=data, timeout=600)
    except Exception as e:
        msg = f"Facebook upload failed (network error): {repr(e)}"
        res = SocialPostResult(
            platform="facebook",
            success=False,
            message=msg,
            video_path=str(video_path),
            title=title,
            description=description,
            extra={"file_url": file_url},
        )
        _log_result(res)
        return res

    if response.status_code != 200:
        msg = (
            f"Facebook upload failed: HTTP {response.status_code} "
            f"response={response.text}"
        )
        res = SocialPostResult(
            platform="facebook",
            success=False,
            message=msg,
            video_path=str(video_path),
            title=title,
            description=description,
            extra={"file_url": file_url},
        )
        _log_result(res)
        return res

    json_data: Dict[str, Any] = {}
    try:
        json_data = response.json()
    except Exception:
        pass

    video_id = json_data.get("id")
    extra = {
        "video_id": video_id,
        "graph_response": json_data,
        "file_url": file_url,
    }

    res = SocialPostResult(
        platform="facebook",
        success=True,
        message="Facebook Page video (via file_url) upload completed.",
        video_path=str(video_path),
        title=title,
        description=description,
        extra=extra,
    )
    _log_result(res)
    return res


def _post_to_instagram_via_url(
    video_path: Path,
    title: str,
    description: str,
) -> SocialPostResult:
    
    ig_user_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    access_token = (
        os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
        or os.getenv("INSTAGRAM_ACCESS_TOKEN")
    )
    video_url = _public_url_for_file(video_path)

    if not ig_user_id or not access_token:
        msg = (
            "Missing Instagram credentials. Set INSTAGRAM_BUSINESS_ACCOUNT_ID "
            "and FACEBOOK_PAGE_ACCESS_TOKEN (or INSTAGRAM_ACCESS_TOKEN) in .env "
            "to enable Instagram uploads."
        )
        res = SocialPostResult(
            platform="instagram",
            success=False,
            message=msg,
            video_path=str(video_path),
            title=title,
            description=description,
            extra=None,
        )
        _log_result(res)
        return res

    if not video_url:
        msg = (
            "SOCIAL_PUBLIC_BASE_URL is not configured, so I cannot build a "
            "public video_url for Instagram. Configure SOCIAL_PUBLIC_BASE_URL "
            "in .env."
        )
        res = SocialPostResult(
            platform="instagram",
            success=False,
            message=msg,
            video_path=str(video_path),
            title=title,
            description=description,
            extra={"hint": "Need SOCIAL_PUBLIC_BASE_URL"},
        )
        _log_result(res)
        return res

    caption = f"{title}\n\n{description}".strip()

   
    create_url = f"https://graph.facebook.com/v18.0/{ig_user_id}/media"
    create_data = {
        "media_type": "VIDEO",
        "video_url": video_url,
        "caption": caption,
        "access_token": access_token,
    }

    try:
        create_resp = requests.post(create_url, data=create_data, timeout=600)
    except Exception as e:
        msg = f"Instagram media creation failed (network error): {repr(e)}"
        res = SocialPostResult(
            platform="instagram",
            success=False,
            message=msg,
            video_path=str(video_path),
            title=title,
            description=description,
            extra={"video_url": video_url},
        )
        _log_result(res)
        return res

    if create_resp.status_code != 200:
        msg = (
            f"Instagram media creation failed: HTTP {create_resp.status_code} "
            f"response={create_resp.text}"
        )
        res = SocialPostResult(
            platform="instagram",
            success=False,
            message=msg,
            video_path=str(video_path),
            title=title,
            description=description,
            extra={"video_url": video_url},
        )
        _log_result(res)
        return res

    create_json: Dict[str, Any] = {}
    try:
        create_json = create_resp.json()
    except Exception:
        pass

    creation_id = create_json.get("id")
    if not creation_id:
        msg = "Instagram media creation succeeded but no creation_id returned."
        res = SocialPostResult(
            platform="instagram",
            success=False,
            message=msg,
            video_path=str(video_path),
            title=title,
            description=description,
            extra={"create_response": create_json, "video_url": video_url},
        )
        _log_result(res)
        return res

   
    publish_url = f"https://graph.facebook.com/v18.0/{ig_user_id}/media_publish"
    publish_data = {
        "creation_id": creation_id,
        "access_token": access_token,
    }

    try:
        publish_resp = requests.post(publish_url, data=publish_data, timeout=600)
    except Exception as e:
        msg = f"Instagram publish failed (network error): {repr(e)}"
        res = SocialPostResult(
            platform="instagram",
            success=False,
            message=msg,
            video_path=str(video_path),
            title=title,
            description=description,
            extra={"creation_id": creation_id},
        )
        _log_result(res)
        return res

    if publish_resp.status_code != 200:
        msg = (
            f"Instagram publish failed: HTTP {publish_resp.status_code} "
            f"response={publish_resp.text}"
        )
        res = SocialPostResult(
            platform="instagram",
            success=False,
            message=msg,
            video_path=str(video_path),
            title=title,
            description=description,
            extra={
                "creation_id": creation_id,
                "video_url": video_url,
                "publish_raw": publish_resp.text,
            },
        )
        _log_result(res)
        return res

    publish_json: Dict[str, Any] = {}
    try:
        publish_json = publish_resp.json()
    except Exception:
        pass

    extra = {
        "creation_id": creation_id,
        "instagram_post_id": publish_json.get("id"),
        "video_url": video_url,
        "create_response": create_json,
        "publish_response": publish_json,
    }

    res = SocialPostResult(
        platform="instagram",
        success=True,
        message="Instagram video published successfully via video_url.",
        video_path=str(video_path),
        title=title,
        description=description,
        extra=extra,
    )
    _log_result(res)
    return res


def _post_to_tiktok_stub(
    video_path: Path,
    title: str,
    description: str,
) -> SocialPostResult:
   
    msg = (
        "TikTok auto-post is not implemented yet. The backend logged this "
        "attempt in out/social_logs/. Once you have a TikTok API key, "
        "replace _post_to_tiktok_stub with the real upload flow."
    )

    res = SocialPostResult(
        platform="tiktok",
        success=False,
        message=msg,
        video_path=str(video_path),
        title=title,
        description=description,
        extra=None,
    )
    _log_result(res)
    return res


def post_to_platform(
    platform: str,
    video_path: Path,
    title: str,
    description: str,
) -> Dict[str, Any]:
    
    normalized = platform.lower().strip()

    if normalized == "youtube":
        res = _upload_to_youtube(video_path, title, description)
        return asdict(res)

    if normalized == "facebook":
        res = _post_to_facebook_page_via_url(video_path, title, description)
        return asdict(res)

    if normalized == "instagram":
        res = _post_to_instagram_via_url(video_path, title, description)
        return asdict(res)

    if normalized == "tiktok":
        res = _post_to_tiktok_stub(video_path, title, description)
        return asdict(res)

    # Fallback for unknown platforms
    msg = (
        f"Real upload for '{platform}' not implemented. "
        f"Action logged only."
    )
    res = SocialPostResult(
        platform=normalized,
        success=False,
        message=msg,
        video_path=str(video_path),
        title=title,
        description=description,
        extra=None,
    )
    _log_result(res)
    return asdict(res)
