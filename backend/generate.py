from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any

from moviepy.editor import AudioFileClip

from .story import load_metadata, build_story
from .audio import synth_voiceover, build_audio_track
from .edit import collect_clips, pick_visuals, assemble_video
from .config import SETTINGS, PetProjectConfig


@dataclass
class GenResult:
    success: bool
    message: Optional[str]
    outfile: Optional[Path]
    duration: Optional[float]
    tone_arc: Optional[str]
    story_title: Optional[str]


def generate_video(cfg: PetProjectConfig, out_path: Path) -> GenResult:
   

    cfg.validate()
    pet_dir = cfg.pet_dir

    
    try:
        metadata: Dict[str, Any] = load_metadata(pet_dir)
    except Exception as e:
        return GenResult(
            success=False,
            message=f"Failed to load metadata: {repr(e)}",
            outfile=None,
            duration=None,
            tone_arc=None,
            story_title=None,
        )

    pet_name = metadata.get("name", "Friend")

    
    try:
        story = build_story(metadata)
    except Exception as e:
        return GenResult(
            success=False,
            message=f"Story generation failed: {repr(e)}",
            outfile=None,
            duration=None,
            tone_arc=None,
            story_title=None,
        )

    
    voice_file: Optional[Path] = None
    voice_duration: Optional[float] = None

    if cfg.use_tts:
        try:
            voice_dir = SETTINGS.base_output_dir / "voiceovers"
            voice_dir.mkdir(parents=True, exist_ok=True)

            voice_file = synth_voiceover(
                text=story.script,
                out_dir=voice_dir,
                speed=cfg.tts_speed,
            )

            try:
                with AudioFileClip(str(voice_file)) as vo_clip:
                    voice_duration = float(vo_clip.duration or 0.0)
            except Exception as e:
                print("[generate.py] Warning: could not measure TTS duration:", e)
                voice_duration = None

        except Exception as e:
            print("[generate.py] Warning: TTS failed:", e)
            voice_file = None
            voice_duration = None

    
    def _compute_effective_duration() -> float:
        pad = 1.0
        if voice_duration is not None and voice_duration > 0:
            return min(float(cfg.target_duration), float(voice_duration) + pad)
        return float(cfg.target_duration)

    effective_duration = _compute_effective_duration()

    print(
        f"[generate.py] target={cfg.target_duration:.2f}s, "
        f"voice={voice_duration if voice_duration is not None else 'N/A'}s, "
        f"effective={effective_duration:.2f}s"
    )


    clips_dir = pet_dir / "Clips"
    clip_paths = collect_clips(clips_dir)

    if not clip_paths:
        return GenResult(
            success=False,
            message=f"No video clips found in {clips_dir}",
            outfile=None,
            duration=None,
            tone_arc=None,
            story_title=None,
        )

    visuals = pick_visuals(clip_paths, effective_duration)

    if not visuals:
        return GenResult(
            success=False,
            message="All clips were unreadable — cannot build video.",
            outfile=None,
            duration=None,
            tone_arc=None,
            story_title=None,
        )

    total_visual_duration = sum(c.duration for c in visuals)

    print(
        f"[generate.py] visuals≈{total_visual_duration:.2f}s "
        f"(requested≈{effective_duration:.2f}s)"
    )

    
    audio_file: Optional[Path] = None

    try:
        if voice_file and voice_file.exists():
            mix_clip = None
            try:
                print("[generate.py] Trying to build voice+music mix...")
                mix_clip = build_audio_track(
                    total_visual_duration=effective_duration,
                    voice_file=voice_file,
                    music_file=None,
                )
            except MemoryError:
                print("[generate.py] Music mix MemoryError, using voice only.")
                mix_clip = None
            except Exception as e:
                print("[generate.py] Music mix failed:", e)
                mix_clip = None

            if mix_clip is not None:
                audio_dir = SETTINGS.base_output_dir / "audio"
                audio_dir.mkdir(parents=True, exist_ok=True)
                audio_file = audio_dir / f"{pet_dir.name}_mix.mp3"
                mix_clip.write_audiofile(str(audio_file), fps=22050)
                mix_clip.close()
            else:
                audio_file = voice_file
        else:
            audio_file = None

    except Exception as e:
        print("[generate.py] Warning: audio setup failed:", e)
        if voice_file and voice_file.exists():
            audio_file = voice_file
        else:
            audio_file = None

   
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        final_path = assemble_video(
            pet_name=pet_name,
            visuals=visuals,
            tone=story.tone_arc,
            aspect=cfg.aspect,
            audio_file=audio_file,
            out_path=out_path,
            script=story.script,
        )
    except MemoryError:
        msg = (
            "Rendering failed due to insufficient memory. "
            "Try shorter clips, a smaller target duration, or a smaller aspect/resolution."
        )
        return GenResult(
            success=False,
            message=msg,
            outfile=None,
            duration=None,
            tone_arc=story.tone_arc,
            story_title=story.title,
        )
    except Exception as e:
        msg = f"Rendering failed: {repr(e)}"
        fallback = out_path if out_path.exists() and out_path.stat().st_size > 0 else None
        return GenResult(
            success=False,
            message=msg,
            outfile=fallback,
            duration=None,
            tone_arc=story.tone_arc,
            story_title=story.title,
        )

    return GenResult(
        success=True,
        message="Video generated successfully.",
        outfile=final_path,
        duration=effective_duration,
        tone_arc=story.tone_arc,
        story_title=story.title,
    )
