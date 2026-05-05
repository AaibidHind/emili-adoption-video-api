from __future__ import annotations
from pathlib import Path
from typing import Dict


def publish_facebook(video_path: str, title: str, description: str, hashtags: list) -> Dict:
    """Delegates to the full implementation in backend/social.py."""
    try:
        from backend.social import _post_to_facebook_page_via_url
        full_desc = (description + "\n\n" + " ".join(f"#{h}" for h in hashtags)).strip() if hashtags else description
        result = _post_to_facebook_page_via_url(Path(video_path), title, full_desc)
        return {"ok": result.success, "message": result.message}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def publish_instagram(video_path: str, title: str, description: str, hashtags: list) -> Dict:
    """Delegates to the full implementation in backend/social.py."""
    try:
        from backend.social import _post_to_instagram_via_url
        full_desc = (description + "\n\n" + " ".join(f"#{h}" for h in hashtags)).strip() if hashtags else description
        result = _post_to_instagram_via_url(Path(video_path), title, full_desc)
        return {"ok": result.success, "message": result.message}
    except Exception as e:
        return {"ok": False, "error": str(e)}
