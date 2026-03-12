from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="Emili TikTok Verification Service")

@app.get("/")
def home():
    return HTMLResponse("""
    <html>
      <head><title>Emili TikTok Integration</title></head>
      <body>
        <h1>Emili TikTok Integration</h1>
        <p>This service is used for TikTok domain verification and OAuth callback handling.</p>
      </body>
    </html>
    """)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/terms")
def terms():
    return HTMLResponse("""
    <html>
      <head><title>Terms of Service</title></head>
      <body>
        <h1>Terms of Service</h1>
        <p>Emili Terms of Service.</p>
      </body>
    </html>
    """)

@app.get("/privacy")
def privacy():
    return HTMLResponse("""
    <html>
      <head><title>Privacy Policy</title></head>
      <body>
        <h1>Privacy Policy</h1>
        <p>Emili Privacy Policy.</p>
      </body>
    </html>
    """)

@app.get("/tiktokyzM3x8mwviIX8D2GfWarSVk6vxFnSKB5.txt")
def verify_tiktok_second():
    return Response(
        content="tiktok-developers-site-verification=yzM3x8mwviIX8D2GfWarSVk6vxFnSKB5",
        media_type="text/plain"
    )

@app.get("/auth/tiktok/callback")
def tiktok_callback(code: str = "", state: str = "", error: str = "", error_description: str = ""):
    return JSONResponse({
        "status": "ok",
        "message": "TikTok callback received",
        "code": code,
        "state": state,
        "error": error,
        "error_description": error_description
    })
