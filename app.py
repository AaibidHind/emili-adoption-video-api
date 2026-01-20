from __future__ import annotations

from pathlib import Path
import os

import streamlit as st

from backend.generate import generate_video
from backend.config import PROJECT_ROOT, PetProjectConfig
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


openai_key = os.getenv("OPENAI_API_KEY")
chat_model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
tts_model = os.getenv("OPENAI_TTS_MODEL", "tts-1")
tts_voice = os.getenv("OPENAI_TTS_VOICE", "alloy")

with st.expander("Runtime configuration", expanded=False):
    if openai_key:
        st.success("OPENAI_API_KEY detected")
    else:
        st.error("OPENAI_API_KEY is NOT set — generation will fail until this is configured.")
    st.write(f"Chat model: `{chat_model}`")
    st.write(f"TTS model: `{tts_model}`")
    st.write(f"TTS voice: `{tts_voice}`")

st.sidebar.header("Settings")

default_pet_folder = PROJECT_ROOT / "examples" / "pets" / "Bruno"

pet_folder_str = st.sidebar.text_input(
    "Pet folder",
    value=str(default_pet_folder),
    help="Folder containing metadata.json and Clips/ subfolder for this pet.",
)

logo_path_str = st.sidebar.text_input(
    "Brand logo (optional)",
    value=str(PROJECT_ROOT / "assets" / "branding" / "logo.png"),
    help="PNG logo for intro/outro cards (future extension).",
)

music_folder_str = st.sidebar.text_input(
    "Music folder",
    value=str(PROJECT_ROOT / "assets" / "music"),
    help="Folder with background music tracks.",
)

aspect = st.sidebar.selectbox(
    "Aspect ratio",
    options=["vertical", "square", "landscape"],
    index=0,
)

target_duration = st.sidebar.slider(
    "Target duration (seconds)",
    min_value=20,
    max_value=60,
    value=40,
    step=5,
)

fps = st.sidebar.slider(
    "FPS (hint for pacing)",
    min_value=24,
    max_value=60,
    value=30,
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

st.sidebar.subheader("Publishing")
auto_post = st.sidebar.checkbox(
    "Auto-post right after generation (use with care)",
    value=False,
    help="If enabled and posting is implemented, the system will publish as soon as the video is generated.",
)


col_left, col_right = st.columns([1, 1.3])


with col_left:
    st.subheader("Inputs")

    pet_dir = Path(pet_folder_str).expanduser().resolve()
    clips_dir = pet_dir / "Clips"

    st.code(f"pet_dir = {pet_dir}", language="bash")
    st.code(f"clips_dir = {clips_dir}", language="bash")

    problems: list[str] = []

    if not pet_dir.exists():
        problems.append("Pet folder not found on disk.")
        st.error("Pet folder not found. Please correct the path in the sidebar.")
    else:
        meta_path = pet_dir / "metadata.json"
        if meta_path.exists():
            st.markdown(f"Metadata: `{meta_path}`")
        else:
            problems.append("metadata.json is missing.")
            st.warning("metadata.json not found in pet folder.")

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
            problems.append("No video clips in Clips/.")
            st.warning("No video clips found in Clips/ subfolder.")

    if problems:
        st.info("Before generating, please fix the issues above so the AI has both metadata and clips.")


with col_right:
    st.subheader("Generated Video")

    output_placeholder = st.empty()
    meta_placeholder = st.empty()

    generate_clicked = st.button("Generate Video", use_container_width=True)

    if generate_clicked:
        if not openai_key:
            output_placeholder.error("Missing OPENAI_API_KEY — please configure the server first.")
        elif not pet_dir.exists():
            output_placeholder.error("Pet folder does not exist. Fix the path and try again.")
        else:
            cfg = PetProjectConfig(
                pet_dir=pet_dir,
                logo_path=Path(logo_path_str) if logo_path_str else None,
                music_dir=Path(music_folder_str) if music_folder_str else None,
                aspect=aspect,
                target_duration=target_duration,
                fps=fps,
                use_tts=use_tts,
                tts_speed=tts_speed,
                auto_post=auto_post,
            )

            out_dir = PROJECT_ROOT / "out"
            out_dir.mkdir(parents=True, exist_ok=True)
            
            outfile = out_dir / f"{pet_dir.name}_{aspect}.mp4"

            with st.spinner("Generating video (storyline, TTS, music, editing)..."):
                try:
                    result = generate_video(cfg, outfile)
                except Exception as e:
                    output_placeholder.error("Generation failed with an unexpected error.")
                    meta_placeholder.exception(e)
                else:
                    payload = {
                        "success": getattr(result, "success", False),
                        "message": getattr(result, "message", ""),
                        "duration": getattr(result, "duration", None),
                        "tone_arc": getattr(result, "tone_arc", None),
                        "title": getattr(result, "story_title", None),
                        "outfile": str(getattr(result, "outfile", outfile)),
                    }

                    if not payload["success"]:
                        output_placeholder.error("Generation failed")
                        meta_placeholder.json(payload)
                    else:
                        output_placeholder.success("Video generated successfully")
                        meta_placeholder.json(payload)

                        out_path = Path(payload["outfile"])
                        if out_path.exists():
                            st.video(str(out_path))
                        else:
                            st.warning("Video file path returned, but file not found on disk.")

                       
                        st.session_state["last_video_info"] = {
                            "success": payload["success"],
                            "outfile": payload["outfile"],
                            "title": payload["title"],
                            "description": payload.get("tone_arc") or "",
                        }

st.markdown("---")
st.subheader("Publish to social media")

last_info = st.session_state.get("last_video_info")

if not last_info or not last_info.get("success") or not last_info.get("outfile"):
    st.info("Generate a video first, then you can publish it here.")
else:
    video_path = Path(last_info["outfile"])

    if not video_path.exists():
        st.warning("Generated video file not found on disk. Please generate again.")
    else:
        st.write(f"Ready to publish: `{video_path.name}`")

        platforms = st.multiselect(
       "Select platforms",
        options=["youtube", "facebook", "instagram", "tiktok"],
        default=["youtube"],
        help=(
        "Results are always logged to out/social_logs/. "
        "YouTube / Facebook / Instagram will really publish if credentials "
        "are configured in .env; TikTok is currently a logged stub."
    ),
)  


        publish_clicked = st.button("Publish to selected platforms")

        if publish_clicked:
            if not platforms:
                st.warning("Please select at least one platform.")
            else:
                all_results = []
                for p in platforms:
                    with st.spinner(f"Publishing to {p}..."):
                        res = post_to_platform(
                            platform=p,
                            video_path=video_path,
                            title=last_info.get("title") or video_path.stem,
                            description=last_info.get("description") or "",
                        )
                        all_results.append(res)

                st.success("Publish attempted. Results:")
                for res in all_results:
                    st.json(res)

st.markdown("---")
st.caption("Emili prototype - emotional adoption video generator (GPT-4 + TTS + MoviePy + branding).")
