from __future__ import annotations
from pathlib import Path
from typing import Dict


def publish_youtube(video_path: str, title: str, description: str, hashtags: list) -> Dict:
    """Delegates to the full implementation in backend/social.py."""
    try:
        from backend.social import _upload_to_youtube
        full_desc = (description + "\n\n" + " ".join(f"#{h}" for h in hashtags)).strip() if hashtags else description
        result = _upload_to_youtube(Path(video_path), title, full_desc)
        return {"ok": result.success, "message": result.message, "extra": result.extra}
    except Exception as e:
        return {"ok": False, "error": str(e)}
