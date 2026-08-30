#!/usr/bin/env python3
"""
OmniRoute Web Presentation & Interactive Suite
Ultra-lightweight, high-performance FastAPI server optimized for Render.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

load_dotenv()

app = FastAPI(
    title="OmniRoute Web Showcase",
    description="Product showcase and interactive demo for OmniRoute AI Gateway",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML_PATH = os.path.join(BASE_DIR, "index.html")
ICON_SVG_PATH = os.path.join(BASE_DIR, "icon.svg")


@app.get("/")
async def serve_index():
    """Serve the landing page and autoplay demonstration."""
    if os.path.exists(INDEX_HTML_PATH):
        return FileResponse(INDEX_HTML_PATH, media_type="text/html")
    return JSONResponse({"status": "ok", "message": "OmniRoute Web App running."}, status_code=200)


@app.get("/icon.svg")
async def serve_icon():
    """Serve the Apple-style vector icon."""
    if os.path.exists(ICON_SVG_PATH):
        return FileResponse(ICON_SVG_PATH, media_type="image/svg+xml")
    return JSONResponse({"error": "Icon not found"}, status_code=404)


@app.get("/api/health")
async def health_check():
    """Lightweight health check endpoint for Render."""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "mode": "showcase_and_demo",
        "version": "1.0.0",
    }


@app.get("/api/models")
async def get_models():
    """Return model catalog for the demo."""
    return {
        "connected": True,
        "count": 7,
        "models": [
            {"id": "auto/best-coding", "name": "Auto: Best Coding (Specialist Router)", "provider": "auto", "is_free": True, "is_1m": False},
            {"id": "auto/best-chat", "name": "Auto: Best Chat (Fallback Router)", "provider": "auto", "is_free": True, "is_1m": False},
            {"id": "oc/mimo-v2.5-free", "name": "Mimo v2.5 Free (1M Context)", "provider": "oc", "is_free": True, "is_1m": True},
            {"id": "oc/north-mini-code-free", "name": "North Mini Code Free", "provider": "oc", "is_free": True, "is_1m": False},
            {"id": "oc/nemotron-3-ultra-free", "name": "Nemotron 3 Ultra Free", "provider": "oc", "is_free": True, "is_1m": False},
            {"id": "aug/opus4.8", "name": "Claude Opus 4.8", "provider": "aug", "is_free": False, "is_1m": False},
            {"id": "tllm/gemini_3_pro", "name": "Gemini 3 Pro (1M Context)", "provider": "tllm", "is_free": False, "is_1m": True},
        ]
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Starting OmniRoute Showcase on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
