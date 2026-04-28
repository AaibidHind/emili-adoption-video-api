from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import PROJECT_ROOT, PetProjectConfig
from backend.generate import generate_video

app = FastAPI(title="Emili Video Generator Service")

OUT_DIR = Path("out")
OUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/out", StaticFiles(directory=str(OUT_DIR)), name="out")


@app.get("/health")
def health():
    return {"status": "ok"}


class GenRequest(BaseModel):
    pet_dir: str
    logo_path: Optional[str] = None
    music_dir: Optional[str] = None
    tone: str = "auto"
    fps: int = 24
    target_duration: int = 20
    aspect: str = "vertical"
    use_tts: bool = True
    transcribe_vo: bool = False
    out: Optional[str] = None
    tts_voice: str = "alloy"
    tts_speed: float = 1.0


@app.post("/generate")
def generate(req: GenRequest):
    pet_dir = Path(req.pet_dir)
    if not pet_dir.exists():
        raise HTTPException(status_code=400, detail=f"Pet folder not found: {pet_dir}")

    out_name = f"{pet_dir.name}_{req.aspect}.mp4"
    out_path = OUT_DIR / out_name

    cfg = PetProjectConfig(
        pet_dir=pet_dir,
        logo_path=Path(req.logo_path) if req.logo_path else None,
        music_dir=Path(req.music_dir) if req.music_dir else None,
        aspect=req.aspect,
        target_duration=req.target_duration,
        fps=req.fps,
        use_tts=req.use_tts,
        tts_speed=req.tts_speed,
        tts_voice=req.tts_voice,
        auto_post=False,
    )

    try:
        result = generate_video(cfg, out_path)
    except MemoryError:
        raise HTTPException(status_code=503, detail="Out of memory. Try shorter duration or fewer clips.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {repr(e)}")

    return {
        "success": result.success,
        "message": result.message,
        "outfile": str(result.outfile) if result.outfile else None,
        "outfile_name": out_path.name if result.outfile else None,
        "duration": result.duration,
        "tone_arc": result.tone_arc,
        "story_title": result.story_title,
    }
