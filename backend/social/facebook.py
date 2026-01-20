from __future__ import annotations
import requests, os
from typing import Dict
from ..config import get_settings

def publish_facebook(video_path: str, title: str, description: str, hashtags: list[str]) -> Dict:
    s = get_settings()
    if not (s.fb_page_id and s.fb_access_token):
        return {"ok": False, "error": "FB creds missing"}
    try:
    
        url = f"https://graph.facebook.com/v20.0/{s.fb_page_id}/videos"
        params = {
            "access_token": s.fb_access_token,
            "title": title,
            "description": description + "\n" + " ".join(f"#{h}" for h in hashtags),
        }
        files = {"source": open(video_path, "rb")}
        r = requests.post(url, data=params, files=files, timeout=120)
        return {"ok": r.ok, "status": r.status_code, "resp": r.json() if r.content else {}}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def publish_instagram(video_path: str, title: str, description: str, hashtags: list[str]) -> Dict:
    s = get_settings()
    if not (s.ig_business_id and s.ig_access_token):
        return {"ok": False, "error": "IG creds missing"}
    try:
       
        create_url = f"https://graph.facebook.com/v20.0/{s.ig_business_id}/media"
        caption = title + "\n\n" + description + "\n" + " ".join(f"#{h}" for h in hashtags)
        
        return {"ok": False, "error": "Direct IG video upload requires a public URL. Host the video and supply 'video_url' parameter, or cross-post via FB Page."}
    except Exception as e:
        return {"ok": False, "error": str(e)}
