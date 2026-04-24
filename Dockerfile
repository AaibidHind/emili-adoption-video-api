FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Render uses port 10000 by default for web services
# FastAPI handles /terms, /privacy, /legal — must be on the public port
# Streamlit runs internally on 8501 (not exposed to TikTok)
EXPOSE 10000 8501

CMD ["/bin/bash", "-lc", "streamlit run app.py --server.port 8501 --server.address 0.0.0.0 & uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000}"]
