from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

from openai import OpenAI
from .config import SETTINGS



@dataclass
class StoryResult:
    title: str
    short_title: str
    description: str
    script: str
    tone_arc: str



_client = OpenAI(api_key=SETTINGS.openai_api_key)


def load_metadata(pet_dir: Path) -> Dict[str, Any]:
    
    meta_path = pet_dir / "metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"metadata.json not found in {pet_dir}")

    with meta_path.open("r", encoding="utf-8") as f:
        return json.load(f)

def build_story(metadata: Dict[str, Any]) -> StoryResult:
    """
    Generate:
      - Short emotional script (optimized for ~10–15s TTS)
      - Tone arc
      - Catchy title
    Using the GPT-4o API (or configured chat model).
    """
    name = metadata.get("name", "this pet")
    species = metadata.get("species") or metadata.get("type", "dog")
    age = metadata.get("age", "unknown age")
    temperament = metadata.get("temperament", "gentle and loving")
    shelter_story = metadata.get("story", "")

    chat_model = SETTINGS.openai_chat_model

    script_prompt = f"""
You are a creative director for an animal shelter.

Write a VERY SHORT adoption voiceover script for a {species} named {name}.

Details:
- Age: {age}
- Temperament: {temperament}
- Background: {shelter_story}

Requirements:
- Length: 12–15 seconds of speech (max ~80 words)
- 2 short paragraphs maximum
- Warm, emotional tone (not cheesy)
- Speak directly to the viewer ("you")
- Focus on how {name} will make their life better
- End with a clear call to adopt {name} (e.g., "Come meet {name} today" or "Adopt {name} and give them the home they deserve")
- Do NOT include scene directions or camera instructions
"""

    script_resp = _client.chat.completions.create(
        model=chat_model,
        messages=[
            {"role": "system", "content": "You write emotional but concise adoption narratives, optimized for short social media videos."},
            {"role": "user", "content": script_prompt.strip()},
        ],
        temperature=0.8,
        max_tokens=180,
    )
    script_text = (script_resp.choices[0].message.content or "").strip()

    
    tone_prompt = f"""
Analyze this pet’s metadata:

- Name: {name}
- Species: {species}
- Age: {age}
- Temperament: {temperament}
- Story: {shelter_story}

Return:
1) One short sentence summarizing the overall emotional tone  
   (e.g., "soft and hopeful").
2) Then a list of 3–4 comma-separated keywords describing the emotional progression  
   (e.g., "shy, curious, joyful, hopeful").

Output in one line.
"""

    tone_resp = _client.chat.completions.create(
        model=chat_model,
        messages=[
            {"role": "system", "content": "You describe emotional tone clearly and concisely."},
            {"role": "user", "content": tone_prompt.strip()},
        ],
        temperature=0.7,
        max_tokens=80,
    )

    tone_text = (tone_resp.choices[0].message.content or "").strip()
    tone_arc = " ".join(tone_text.split()) 


    title_prompt = f"""
Create a short, catchy title (max 40 characters) for an adoption video
about a {species} named {name}.

Story context:
{script_text}

Return ONLY the title, no quotes.
"""

    title_resp = _client.chat.completions.create(
        model=chat_model,
        messages=[
            {"role": "system", "content": "You create short, emotional, marketable titles."},
            {"role": "user", "content": title_prompt.strip()},
        ],
        temperature=0.9,
        max_tokens=40,
    )

    title = (title_resp.choices[0].message.content or "").strip().strip('"')
    short_title = title if len(title) <= 40 else title[:37] + "..."

    description = (
        f"{title} — {species.capitalize()} available for adoption.\n\n"
        f"{script_text}"
    )

    return StoryResult(
        title=title,
        short_title=short_title,
        description=description,
        script=script_text,
        tone_arc=tone_arc,
    )
