
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_PATH)



@dataclass
class Settings:
   
    openai_api_key: str
    openai_chat_model: str = "gpt-4o-mini"
    openai_tts_model: str = "tts-1"
    openai_tts_voice: str = "alloy"
    base_output_dir: Path = PROJECT_ROOT / "out"

    @classmethod
    def from_env(cls) -> "Settings":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                f"Missing OPENAI_API_KEY in environment. "
                f"Expected .env at: {ENV_PATH}"
            )

        return cls(
            openai_api_key=key,
            openai_chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
            openai_tts_model=os.getenv("OPENAI_TTS_MODEL", "tts-1"),
            openai_tts_voice=os.getenv("OPENAI_TTS_VOICE", "alloy"),
            base_output_dir=PROJECT_ROOT / os.getenv("OUTPUT_DIR", "out"),
        )


SETTINGS = Settings.from_env()


@dataclass
class PetProjectConfig:
 
    pet_dir: Path
    logo_path: Path | None = None
    music_dir: Path | None = None

    # Video properties
    aspect: str = "vertical"  
    target_duration: int = 40
    fps: int = 30

    # Narration
    use_tts: bool = True
    tts_speed: float = 1.0
    tts_voice: str = "alloy"
    transcribe_vo: bool = False
    tone: str = "auto"

    # Publishing
    auto_post: bool = False
    def validate(self) -> None:
       
        # Normalize to Path
        if isinstance(self.pet_dir, str):
            self.pet_dir = Path(self.pet_dir).expanduser().resolve()

        if self.logo_path and isinstance(self.logo_path, str):
            self.logo_path = Path(self.logo_path).expanduser().resolve()

        if self.music_dir and isinstance(self.music_dir, str):
            self.music_dir = Path(self.music_dir).expanduser().resolve()

     
        if not self.pet_dir.exists():
            raise FileNotFoundError(f"Pet directory does not exist: {self.pet_dir}")

   
