
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    afx,
    concatenate_audioclips,
)

from openai import OpenAI
from .config import SETTINGS, PROJECT_ROOT

client = OpenAI(api_key=SETTINGS.openai_api_key)


def synth_voiceover(text: str, out_dir: Path, speed: float = 1.0) -> Path:
   

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "voiceover.mp3"

    # Send text → TTS
    resp = client.audio.speech.create(
        model=SETTINGS.openai_tts_model,
        voice=SETTINGS.openai_tts_voice,
        input=text,
    )

    # Save generated MP3
    resp.stream_to_file(str(out_path))

    # Apply speed adjustment via MoviePy
    if speed != 1.0:
        clip = AudioFileClip(str(out_path))
        modified = clip.fx(afx.speedx, speed)

        modified.write_audiofile(str(out_path), fps=44100)

        clip.close()
        modified.close()

    return out_path

def _find_default_music() -> Optional[Path]:
   
    music_root = PROJECT_ROOT / "assets" / "music"
    if not music_root.exists():
        return None

    candidates = list(music_root.rglob("*.mp3")) + list(music_root.rglob("*.wav"))
    if not candidates:
        return None

    candidates.sort()
    return candidates[0]



def build_audio_track(
    total_visual_duration: float,
    voice_file: Optional[Path],
    music_file: Optional[Path],
) -> Optional[CompositeAudioClip]:
  

    audio_clips = []

    
    if voice_file:
        try:
            vo = AudioFileClip(str(voice_file))
            audio_clips.append(vo)
        except Exception as e:
            print(f"[audio.py] Warning: could not load voiceover: {e}")

    if music_file is None:
        music_file = _find_default_music()

    if music_file:
        try:
            music = AudioFileClip(str(music_file))

           
            if music.duration < total_visual_duration:  
                loops = int(total_visual_duration // music.duration) + 1
                music = concatenate_audioclips([music] * loops)

            
            music = music.subclip(0, total_visual_duration)

            
            music = music.volumex(0.25).audio_fadein(1).audio_fadeout(1)

            audio_clips.append(music)

        except Exception as e:
            print(f"[audio.py] Warning: could not load music: {e}")

    
    if not audio_clips:
        return None

    try:
        final = CompositeAudioClip(audio_clips).set_duration(total_visual_duration)
        return final
    except Exception as e:
        print(f"[audio.py] Error building audio track: {e}")
        return None
