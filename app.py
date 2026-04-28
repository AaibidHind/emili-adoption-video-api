from __future__ import annotations

from pathlib import Path
import os
import shutil

import requests
import streamlit as st

from backend.config import PROJECT_ROOT
from backend.social import post_to_platform


st.set_page_config(
    page_title="Emili - Adoption Video Generator",
    layout="wide",
)

st.title("Emili - Adoption Video Generator")
st.caption(
    "AI-powered, emotional adoption videos from shelter metadata, with narration, "
    "music, branding, and optional social posting."
)

GENERATOR_URL = os.getenv("GENERATOR_URL", "https://emili-generator.onrender.com")

openai_key = os.getenv("OPENAI_API_KEY")

with st.expander("Runtime configuration", expanded=False):
    if openai_key:
        st.success("OPENAI_API_KEY detected")
    else:
        st.warning("OPENAI_API_KEY not set here — should be set on the generator service.")
    st.write(f"Generator service: `{GENERATOR_URL}`")

st.sidebar.header("Settings")

default_pet_folder = PROJECT_ROOT / "examples" / "pets" / "Bruno"

pet_folder_str = st.sidebar.text_input(
    "Pet folder",
    value=str(default_pet_folder),
)

logo_path_str = st.sidebar.text_input(
    "Brand logo (optional)",
    value=str(PROJECT_ROOT / "assets" / "branding" / "logo.png"),
)

music_folder_str = st.sidebar.text_input(
    "Music folder",
    value=str(PROJECT_ROOT / "assets" / "music"),
)

aspect = st.sidebar.selectbox(
    "Aspect ratio",
    options=["vertical", "square", "landscape"],
    index=0,
)

target_duration = st.sidebar.slider(
    "Target duration (seconds)",
    min_value=10,
    max_value=30,
    value=20,
    step=5,
)

st.sidebar.subheader("Audio")
use_tts = st.sidebar.checkbox("Generate narration with TTS", value=True)
tts_speed = st.sidebar.slider(
    "TTS speed",
    min_value=0.8,
    max_value=1.3,
    value=1.0,
    step=0.05,
)

col_left, col_right = st.columns([1, 1.3])

with col_left:
    st.subheader("Inputs")

    pet_dir = Path(pet_folder_str).expanduser().resolve()
    clips_dir = pet_dir / "Clips"

    st.code(f"pet_dir = {pet_dir}", language="bash")
    st.code(f"clips_dir = {clips_dir}", language="bash")

    if not pet_dir.exists():
        st.error("Pet folder not found.")
    else:
        meta_path = pet_dir / "metadata.json"
        if meta_path.exists():
            st.markdown(f"Metadata: `{meta_path}`")
        else:
            st.warning("metadata.json not found.")

        clip_files = sorted(
            list(clips_dir.glob("*.mp4"))
            + list(clips_dir.glob("*.mov"))
            + list(clips_dir.glob("*.m4v"))
        )
        if clip_files:
            st.markdown("Video clips found:")
            for c in clip_files:
                st.write(f"- {c.name}")
        else:
            st.warning("No video clips found in Clips/.")

with col_right:
    st.subheader("Generated Video")

    output_placeholder = st.empty()
    meta_placeholder = st.empty()

    generate_clicked = st.button("Generate Video", use_container_width=True)

    if generate_clicked:
        with st.spinner("Sending to generator service..."):
            try:
                resp = requests.post(
                    f"{GENERATOR_URL}/generate",
                    json={
                        "pet_dir": str(pet_dir),
                        "logo_path": logo_path_str or None,
                        "music_dir": music_folder_str or None,
                        "aspect": aspect,
                        "target_duration": target_duration,
                        "fps": 24,
                        "use_tts": use_tts,
                        "tts_speed": tts_speed,
                        "tts_voice": "alloy",
                    },
                    timeout=600
                )
                payload = resp.json()
            except Exception as e:
                output_placeholder.error(f"Could not reach generator service: {e}")
                payload = None

        if payload:
            if not payload.get("success"):
                output_placeholder.error("Generation failed")
                meta_placeholder.json(payload)
            else:
                output_placeholder.success("Video generated successfully!")
                meta_placeholder.json(payload)

                outfile_name = payload.get("outfile_name")
                if outfile_name:
                    video_url = f"{GENERATOR_URL}/out/{outfile_name}"
                    st.video(video_url)

                    st.session_state["last_video_info"] = {
                        "success": True,
                        "outfile": payload.get("outfile"),
                        "outfile_name": outfile_name,
                        "video_url": video_url,
                        "title": payload.get("story_title"),
                        "description": payload.get("tone_arc") or "",
                    }

st.markdown("---")
st.subheader("Publish to social media")

last_info = st.session_state.get("last_video_info")

if not last_info or not last_info.get("success"):
    st.info("Generate a video first, then you can publish it here.")
else:
    outfile_name = last_info.get("outfile_name")
    video_url = last_info.get("video_url")

    if not outfile_name:
        st.warning("No video available. Please generate again.")
    else:
        st.write(f"Ready to publish: `{outfile_name}`")
        st.write(f"Video URL: `{video_url}`")

        platforms = st.multiselect(
            "Select platforms",
            options=["youtube", "facebook", "instagram", "tiktok"],
            default=["tiktok"],
        )

        publish_clicked = st.button("Publish to selected platforms")

        if publish_clicked:
            if not platforms:
                st.warning("Please select at least one platform.")
            else:
                # Download video from generator to local for publishing
                try:
                    with st.spinner("Downloading video for publishing..."):
                        r = requests.get(video_url, timeout=120)
                        local_path = Path("out") / outfile_name
                        local_path.parent.mkdir(exist_ok=True)
                        local_path.write_bytes(r.content)

                        static_dir = Path("static")
                        static_dir.mkdir(exist_ok=True)
                        shutil.copy(local_path, static_dir / outfile_name)
                except Exception as e:
                    st.error(f"Failed to download video: {e}")
                    local_path = None

                if local_path and local_path.exists():
                    all_results = []
                    for p in platforms:
                        with st.spinner(f"Publishing to {p}..."):
                            res = post_to_platform(
                                platform=p,
                                video_path=local_path,
                                title=last_info.get("title") or outfile_name,
                                description=last_info.get("description") or "",
                            )
                            all_results.append(res)

                    st.success("Publish attempted. Results:")
                    for res in all_results:
                        st.json(res)

st.markdown("---")
st.caption("Emili prototype - emotional adoption video generator (GPT-4 + TTS + MoviePy + branding).")
