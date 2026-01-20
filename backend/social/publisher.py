from __future__ import annotations
from typing import List
from .youtube import publish_youtube
from .facebook import publish_facebook, publish_instagram
from .tiktok import publish_tiktok

def publish(video_path: str, title: str, description: str, hashtags: list[str], targets: List[str]) -> dict:
    results = {}
    if "youtube" in targets:
        results["youtube"] = publish_youtube(video_path, title, description, hashtags)
    if "facebook" in targets:
        results["facebook"] = publish_facebook(video_path, title, description, hashtags)
    if "instagram" in targets:
        results["instagram"] = publish_instagram(video_path, title, description, hashtags)
    if "tiktok" in targets:
        results["tiktok"] = publish_tiktok(video_path, title, description, hashtags)
    return results
