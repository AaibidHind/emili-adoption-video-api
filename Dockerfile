FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y ffmpeg fonts-liberation && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Port 8080 = FastAPI (public, handles /terms /privacy /auth etc.)
# Port 8501 = Streamlit (internal only, proxied through FastAPI)
EXPOSE 8080

CMD ["/bin/bash", "-lc", "streamlit run app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true --server.enableCORS false --server.enableXsrfProtection false & sleep 4 && uvicorn server:app --host 0.0.0.0 --port 8080"]
