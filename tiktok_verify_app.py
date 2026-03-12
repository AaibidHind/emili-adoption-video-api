from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

app = FastAPI(title="Emili TikTok Verification Service")


@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return HTMLResponse("""
    <html>
      <head><title>Emili TikTok Integration</title></head>
      <body>
        <h1>Emili TikTok Integration</h1>
        <p>This service is used for TikTok domain verification.</p>
      </body>
    </html>
    """)


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return JSONResponse({"status": "ok"})


@app.api_route("/terms", methods=["GET", "HEAD"])
def terms():
    return HTMLResponse("""
    <html>
      <body>
        <h1>Terms of Service</h1>
        <p>Emili Terms of Service.</p>
      </body>
    </html>
    """)


@app.api_route("/privacy", methods=["GET", "HEAD"])
def privacy():
    return HTMLResponse("""
    <html>
      <body>
        <h1>Privacy Policy</h1>
        <p>Emili Privacy Policy.</p>
      </body>
    </html>
    """)


# TikTok verification file
@app.api_route("/tiktokyzM3x8mwvilX8D2GfWarSVk6vxFnSKB5.txt", methods=["GET", "HEAD"])
def verify_tiktok():
    return PlainTextResponse(
        "tiktok-developers-site-verification=yzM3x8mwvilX8D2GfWarSVk6vxFnSKB5"
    )


@app.api_route("/auth/tiktok/callback", methods=["GET", "HEAD"])
def tiktok_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = ""
):
    return JSONResponse({
        "status": "ok",
        "message": "TikTok callback received",
        "code": code,
        "state": state,
        "error": error,
        "error_description": error_description
    })
