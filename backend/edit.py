from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
import traceback

from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    CompositeVideoClip,
    concatenate_videoclips,
)

from .subtitles import build_subtitle_clips

print("[edit.py] LOADED VERSION P10 (low-memory + Netflix subtitles)")



@dataclass
class StreamClip:
    path: Path
    duration: float
    start: float = 0.0
    end: Optional[float] = None  

def collect_clips(clips_dir: Path) -> List[Path]:
    print(f"[edit.py] Using collect_clips from: {__file__}")
    if not clips_dir.exists():
        print(f"[edit.py] Clips dir does not exist: {clips_dir}")
        return []

    exts = [".mp4", ".mov", ".m4v"]
    files = [p for p in sorted(clips_dir.iterdir()) if p.is_file() and p.suffix.lower() in exts]

    print(f"[edit.py] Found {len(files)} candidate clips.")
    for f in files:
        print("  -", f)
    return files
def _safe_probe_duration(path: Path) -> float:
    
    try:
        print(f"[edit.py] Probing clip: {path}")
        with VideoFileClip(str(path)) as v:
            _ = v.get_frame(0)
            d = float(v.duration or 0)
            print(f"[edit.py]   OK, duration = {d:.2f}s")
            return d
    except Exception as e:
        print(f"[WARNING] Unreadable clip at probe: {path} | Error: {e}")
        return 0.0


def pick_visuals(clip_paths: List[Path], target_duration: float) -> List[StreamClip]:
    print(f"[edit.py] Picking visuals up to ~{target_duration:.2f}s")
    visuals: List[StreamClip] = []
    total = 0.0

    for path in clip_paths:
        dur = _safe_probe_duration(path)
        if dur <= 0:
            continue

        # If adding full clip would overshoot, trim it
        if total + dur > target_duration:
            dur = max(0.0, target_duration - total)

        if dur <= 0:
            break

        visuals.append(StreamClip(path=path, duration=dur))
        total += dur

        if total >= target_duration:
            break

    print(f"[edit.py] Selected {len(visuals)} clips, total ~{total:.2f}s (possibly trimmed)")
    return visuals



def _scale_for_aspect(aspect: str) -> Tuple[int, int]:
    """
    Return target resolution. Very low to avoid memory issues.
    """
    a = (aspect or "").lower()
    if a in {"vertical", "portrait"}:
        return (360, 640)       
    if a == "square":
        return (480, 480)       
    return (640, 360)           

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

    print(f"[edit.py] Assembling video for {pet_name} with {len(visuals)} clips.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    error_log = out_path.parent / "video_error.log"

    clips: List[VideoFileClip] = []
    audio_clip: Optional[AudioFileClip] = None
    final_clip = None

    width, height = _scale_for_aspect(aspect)

    try:
       
        for sc in visuals:
            try:
                print(f"[edit.py] Loading clip: {sc.path}")
                v = VideoFileClip(str(sc.path), audio=False)
            except Exception as e:
                print(f"[WARNING] Skipping unreadable clip at load: {sc.path} | {e}")
                continue

            # Trim to requested duration if needed
            try:
                if sc.duration and v.duration and sc.duration < v.duration:
                    v = v.subclip(0, sc.duration)
            except Exception as e:
                print(f"[WARNING] Could not trim clip {sc.path}: {e}")

            v = v.resize((width, height))
            clips.append(v)

        if not clips:
            raise RuntimeError("assemble_video: no clips survived loading")

        concatenated = concatenate_videoclips(clips, method="chain")
        print(f"[edit.py] Concatenated OK: {concatenated.duration:.2f}s")

        final_clip = concatenated

   
        if audio_file and audio_file.exists():
            audio_clip = AudioFileClip(str(audio_file))

            vdur = float(final_clip.duration or 0.0)
            adur = float(audio_clip.duration or 0.0)

            print(f"[edit.py] video={vdur:.2f}, audio={adur:.2f}")

            if adur > 0:
                sync = min(vdur, adur)

                if vdur > sync:
                    print(f"[edit.py] Trimming video to {sync:.2f}s to match audio")
                    final_clip = final_clip.subclip(0, sync)

                if adur > sync:
                    print(f"[edit.py] Trimming audio to {sync:.2f}s to match video")
                    audio_clip = audio_clip.subclip(0, sync)

                final_clip = final_clip.set_audio(audio_clip)

      
        if script:
            try:
                print("[edit.py] Generating PIL subtitle clips...")
                subs = build_subtitle_clips(
                    script=script,
                    total_duration=float(final_clip.duration or 0.0),
                    width=width,
                    height=height,
                )
                if subs:
                    final_clip = CompositeVideoClip([final_clip, *subs])
                else:
                    print("[edit.py] No subtitles generated.")
            except Exception:
                error_log.write_text(
                    "Subtitle rendering failed:\n\n" + "".join(traceback.format_exc()),
                    encoding="utf-8",
                )
                print("[edit.py] Subtitles disabled due to error.")

        
        print(f"[edit.py] Writing output: {out_path}")
        final_clip.write_videofile(
            str(out_path),
            codec="libx264",
            audio_codec="aac",
            fps=30,
            preset="medium",
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

    print("[edit.py] Done assemble_video")
    return out_path
