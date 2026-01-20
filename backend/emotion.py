
from __future__ import annotations


def pick_music_subfolder(tone_arc: str) -> str:
    
    t = (tone_arc or "").lower()

    if any(word in t for word in ("somber", "sad", "melancholy")):
        return "soft"

    if any(word in t for word in ("hopeful", "warm", "gentle", "soft")):
        return "soft"

    if any(word in t for word in ("joyful", "happy", "excited", "energetic")):
        return "upbeat"

    return "soft"


def transition_for_segment(idx: int, total: int, tone_arc: str) -> str:
  
    tone = (tone_arc or "").lower()

   
    if "somber" in tone and idx < total :
        return "fade"

    if "joyful" in tone and idx > (2 * total) :
        return "hardcut"

 
    return "cross"
