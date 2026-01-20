from __future__ import annotations

from typing import List
import textwrap
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip


def split_sentences(script: str) -> List[str]:
  
    cleaned = re.sub(r"\[.*?\]", " ", script, flags=re.DOTALL)
    cleaned = re.sub(r"\s+", " ", cleaned)
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [p.strip() for p in parts if p.strip()]


def estimate_sentence_durations(sentences: List[str], total_duration: float) -> List[float]:
    """Distribute subtitle durations across total video length."""
    if not sentences:
        return []

    approx_wps = 2.8  
    raw = []
    for s in sentences:
        n_words = max(1, len(s.split()))
        raw.append(max(1.0, n_words / approx_wps))

    total_raw = sum(raw)
    if total_raw <= 0:
        return [total_duration / len(sentences)] * len(sentences)

    scale = total_duration / total_raw
    return [d * scale for d in raw]


def _measure_text_size(text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    """
    Measure text without using ImageDraw.textsize (Pillow 10+ safe).
    """
    mask = font.getmask(text)
    return mask.size  # (width, height)


def draw_text_with_outline(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font):
    """
    Netflix-ish style: white text with thin black outline.
    """
    outline = 2
    for ox in range(-outline, outline + 1):
        for oy in range(-outline, outline + 1):
            draw.text((x + ox, y + oy), text, font=font, fill="black")
    draw.text((x, y), text, font=font, fill="white")


def make_subtitle_frame(
    text: str,
    width: int,
    height: int,
    fontsize: int = 40,
) -> ImageClip:
    """
    Create a single subtitle frame as a MoviePy ImageClip.
    Simple white-on-black-outline text like Netflix.
    """

    # Transparent RGBA frame
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Font
    try:
        font = ImageFont.truetype("arial.ttf", fontsize)
    except Exception:
        font = ImageFont.load_default()

    # Wrap text (2–3 lines max)
    lines = textwrap.wrap(text, width=36)

    # Compute total text height
    line_sizes = []
    for line in lines:
        w, h = _measure_text_size(line, font)
        line_sizes.append((w, h))
    total_h = sum(h for _, h in line_sizes)

    # Start near bottom
    y = height - total_h - 80

    for (line, (w, h)) in zip(lines, line_sizes):
        x = (width - w) // 2
        draw_text_with_outline(draw, x, y, line, font)
        y += h

    frame_array = np.array(img)
    return ImageClip(frame_array).set_duration(1.0)


def build_subtitle_clips(
    script: str,
    total_duration: float,
    width: int,
    height: int,
):
    """
    Main entry: script → list of ImageClip subtitles (with timings).
    Netflix-style: no emojis, no uppercase emphasis.
    """
    sentences = split_sentences(script)
    if not sentences:
        return []

    durations = estimate_sentence_durations(sentences, total_duration)

    clips: List[ImageClip] = []
    cur = 0.0

    for sentence, dur in zip(sentences, durations):
        
        text = sentence.strip()
        if not text:
            continue

        frame = make_subtitle_frame(text, width, height)

        clip = (
            frame.set_start(cur)
                 .set_duration(dur)
                 .crossfadein(0.15)
                 .crossfadeout(0.15)
        )

        clips.append(clip)
        cur += dur

    return clips
