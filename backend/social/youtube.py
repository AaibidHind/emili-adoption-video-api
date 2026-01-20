from __future__ import annotations
import os, time
from typing import Dict
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from ..config import get_settings

def _get_youtube_service():
    s = get_settings()
    creds = Credentials(
        token=None,
        refresh_token=s.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=s.youtube_client_id,
        client_secret=s.youtube_client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    return build("youtube", "v3", credentials=creds)

def publish_youtube(video_path: str, title: str, description: str, hashtags: list[str]) -> Dict:
    try:
        yt = _get_youtube_service()
        body = {
            "snippet": {
                "title": title,
                "description": description + "\n\n" + " ".join(f"#{h}" for h in hashtags),
                "categoryId": "15"  
            },
            "status": {"privacyStatus": "public"}
        }
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        response = request.execute()
        return {"ok": True, "videoId": response.get("id")}
    except Exception as e:
        return {"ok": False, "error": str(e)}
