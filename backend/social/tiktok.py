from __future__ import annotations
import requests, os
from typing import Dict
from ..config import get_settings

def publish_tiktok(video_path: str, title: str, description: str, hashtags: list[str]) -> Dict:
    s = get_settings()
    if not (s.tiktok_client_key and s.tiktok_access_token):
        return {"ok": False, "error": "TikTok creds missing"}
    try:

        return {"ok": False, "error": "Implement TikTok upload per your app's approved scope. See developer docs."}
    except Exception as e:
        return {"ok": False, "error": str(e)}
