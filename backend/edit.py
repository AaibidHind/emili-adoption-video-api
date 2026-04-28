from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
import traceback
import gc

from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    CompositeVideoClip,
    concatenate_videoclips,
)

from .subtitles import build_subtitle_clips

print("[edit.py] LOADED VERSION P12 (minimum memory)")


@dataclass
class StreamClip:
    path: Path
    duration: float
    start: float = 0.0
    end: Optional[float] = None


def collect_clips(clips_dir: Path) -> List[Path]:
    if not clips_dir.exists():
        return []
    exts = [".mp4", ".mov", ".m4v"]
    files = [p for p in sorted(clips_dir.iterdir()) if p.is_file() and p.suffix.lower() in exts]
    return files


def _safe_probe_duration(path: Path) -> float:
    try:
        with VideoFileClip(str(path)) as v:
            _ = v.get_frame(0)
            d = float(v.duration or 0)
            return d
    except Exception as e:
        print(f"[WARNING] Unreadable clip: {path} | {e}")
        return 0.0


def pick_visuals(clip_paths: List[Path], target_duration: float) -> List[StreamClip]:
    visuals: List[StreamClip] = []
    total = 0.0
    for path in clip_paths:
        dur = _safe_probe_duration(path)
        if dur <= 0:
            continue
        if total + dur > target_duration:
            dur = max(0.0, target_duration - total)
        if dur <= 0:
            break
        visuals.append(StreamClip(path=path, duration=dur))
        total += dur
        if total >= target_duration:
            break
    return visuals


def _scale_for_aspect(aspect: str) -> Tuple[int, int]:
    a = (aspect or "").lower()
    if a in {"vertical", "portrait"}:
        return (240, 426)
    if a == "square":
        return (320, 320)
    return (426, 240)


def assemble_video(
    pet_name: str,
    visuals: List[StreamClip],
    tone: str,
    aspect: str,
    audio_file: Optional[Path],
    out_path: Path,
    script: Optional[str] = None,
) -> Path:

    if not visuals:
        raise RuntimeError("assemble_video: no visuals to assemble")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    clips: List[VideoFileClip] = []
    audio_clip: Optional[AudioFileClip] = None
    final_clip = None

    width, height = _scale_for_aspect(aspect)

    try:
        for sc in visuals:
            try:
                v = VideoFileClip(str(sc.path), audio=False, fps_source="fps")
            except Exception as e:
                print(f"[WARNING] Skipping clip: {sc.path} | {e}")
                continue

            try:
                if sc.duration and v.duration and sc.duration < v.duration:
                    v = v.subclip(0, sc.duration)
            except Exception:
                pass

            v = v.resize((width, height))
            clips.append(v)
            gc.collect()

        if not clips:
            raise RuntimeError("No clips survived loading")

        concatenated = concatenate_videoclips(clips, method="chain")
        final_clip = concatenated
        gc.collect()

        if audio_file and audio_file.exists():
            audio_clip = AudioFileClip(str(audio_file))
            vdur = float(final_clip.duration or 0.0)
            adur = float(audio_clip.duration or 0.0)
            if adur > 0:
                sync = min(vdur, adur)
                if vdur > sync:
                    final_clip = final_clip.subclip(0, sync)
                if adur > sync:
                    audio_clip = audio_clip.subclip(0, sync)
                final_clip = final_clip.set_audio(audio_clip)
            gc.collect()

        # Skip subtitles to save memory
        print(f"[edit.py] Writing output: {out_path}")
        final_clip.write_videofile(
            str(out_path),
            codec="libx264",
            audio_codec="aac",
            fps=24,
            preset="ultrafast",
            audio_fps=48000,
            ffmpeg_params=["-movflags", "+faststart", "-crf", "28"],
            threads=1,
            logger=None,
        )

    finally:
        for c in clips:
            try:
                c.close()
            except Exception:
                pass
        if audio_clip:
            try:
                audio_clip.close()
            except Exception:
                pass
        if final_clip:
            try:
                final_clip.close()
            except Exception:
                pass
        gc.collect()

    return out_path
