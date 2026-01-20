
from __future__ import annotations

from pathlib import Path
from typing import Tuple, Optional

from moviepy.editor import (
    TextClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
)

def _safe_text(
    text: str,
    fontsize: int,
    color: str = "white",
    stroke_color: Optional[str] = None,
    stroke_width: int = 0,
):

    try:
        return TextClip(
            text,
            fontsize=fontsize,
            color=color,
            stroke_color=stroke_color,
            stroke_width=stroke_width,
            method="caption",
            size=(1200, None), 
        )
    except Exception:
       
        return TextClip(
            text,
            fontsize=fontsize,
            color=color,
        )


def intro_card(
    title: str,
    size: Tuple[int, int],
    duration: float = 2.5,
    logo_path: Optional[Path] = None,
):
   

    w, h = size

    bg = ColorClip(size, color=(10, 10, 10)).set_duration(duration)

    title_clip = _safe_text(title, fontsize=70).set_duration(duration)
    title_clip = title_clip.set_position(("center", h * 0.40))

    elements = [bg, title_clip]

    if logo_path and logo_path.exists():
        logo = ImageClip(str(logo_path)).set_duration(duration)
        logo = logo.resize(width=int(w * 0.25))
        logo = logo.set_position(("center", h * 0.65))
        elements.append(logo)

    return CompositeVideoClip(elements)


def cta_card(
    message: str,
    size: Tuple[int, int],
    duration: float = 2.5,
    logo_path: Optional[Path] = None,
):
    

    w, h = size

    bg = ColorClip(size, color=(0, 0, 0)).set_duration(duration)

    title = _safe_text(message, fontsize=60).set_duration(duration)
    title = title.set_position(("center", h * 0.40))

    subtitle = _safe_text(
        "Adopt today on Emili",
        fontsize=40,
        color="white",
    ).set_duration(duration)
    subtitle = subtitle.set_position(("center", h * 0.60))

    elements = [bg, title, subtitle]

    if logo_path and logo_path.exists():
        logo = ImageClip(str(logo_path)).set_duration(duration)
        logo = logo.resize(width=int(w * 0.20))
        logo = logo.set_position(("center", h * 0.78))
        elements.append(logo)

    return CompositeVideoClip(elements)
