import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

app = FastAPI()

OUT_DIR = Path("out")
OUT_DIR.mkdir(exist_ok=True)
app.mount("/out", StaticFiles(directory=str(OUT_DIR)), name="out")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8502)
