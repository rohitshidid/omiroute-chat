#!/usr/bin/env python3
"""
OmniRoute Web App & Streaming Proxy Backend
Optimized for local development and Render deployment.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

DEFAULT_BASE_URL = os.environ.get("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128/v1").rstrip("/")
DEFAULT_API_KEY = os.environ.get("OMNIROUTE_API_KEY", "")
DEFAULT_MODEL = os.environ.get("OMNIROUTE_MODEL", "auto/best-chat")
DEFAULT_SYSTEM = os.environ.get("OMNIROUTE_SYSTEM", "")


def candidate_urls(base: str) -> List[str]:
    """Generate resilient fallback candidates for localhost and 127.0.0.1."""
    base = base.rstrip("/")
    candidates = [base]
    if "localhost" in base:
        candidates.append(base.replace("localhost", "127.0.0.1"))
    elif "127.0.0.1" in base:
        candidates.append(base.replace("127.0.0.1", "localhost"))
    return candidates


app = FastAPI(
    title="OmniRoute Web Chat",
    description="Web chat interface and streaming gateway proxy for OmniRoute",
    version="1.0.0",
)

# Enable CORS for cross-domain flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

INDEX_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    system_prompt: Optional[str] = None
    stream: Optional[bool] = True
    max_tokens: Optional[int] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@app.get("/")
async def serve_index():
    """Serve the single-page frontend application."""
    if os.path.exists(INDEX_HTML_PATH):
        return FileResponse(INDEX_HTML_PATH, media_type="text/html")
    return JSONResponse(
        {"status": "ok", "message": "OmniRoute API is running. index.html not found."},
        status_code=200,
    )


@app.get("/api/health")
async def health_check():
    """Health check endpoint for Render and status monitoring."""
    base_url = os.environ.get("OMNIROUTE_BASE_URL", DEFAULT_BASE_URL)
    is_gateway_up = False
    models_count = 0
    active_url = base_url
    api_key = os.environ.get("OMNIROUTE_API_KEY", DEFAULT_API_KEY)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    for candidate in candidate_urls(base_url):
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{candidate}/models", headers=headers)
                if res.status_code == 200:
                    is_gateway_up = True
                    data = res.json().get("data", [])
                    models_count = len(data)
                    active_url = candidate
                    break
        except Exception:
            continue

    return {
        "status": "healthy",
        "timestamp": time.time(),
        "gateway_connected": is_gateway_up,
        "gateway_url": active_url,
        "default_model": os.environ.get("OMNIROUTE_MODEL", DEFAULT_MODEL),
        "models_count": models_count,
        "auth_configured": bool(api_key),
    }


@app.get("/api/models")
async def get_models(base_url: Optional[str] = None, api_key: Optional[str] = None):
    """Retrieve routable models from OmniRoute gateway with fallback catalog."""
    target_base = (base_url or os.environ.get("OMNIROUTE_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
    target_key = api_key or os.environ.get("OMNIROUTE_API_KEY", DEFAULT_API_KEY)

    headers = {"Content-Type": "application/json"}
    if target_key:
        headers["Authorization"] = f"Bearer {target_key}"

    for candidate in candidate_urls(target_base):
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(f"{candidate}/models", headers=headers)
                if res.status_code == 200:
                    raw_models = res.json().get("data", [])
                    enhanced_models = []
                    for m in raw_models:
                        m_id = m.get("id", "")
                        provider = m_id.split("/")[0] if "/" in m_id else "other"
                        is_free = "free" in m_id.lower() or provider in ["oc", "auto"]
                        is_1m = any(term in m_id.lower() for term in ["mimo", "gemini", "deepseek-v4"])
                        enhanced_models.append({
                            "id": m_id,
                            "name": m.get("name") or m_id,
                            "provider": provider,
                            "is_free": is_free,
                            "is_1m": is_1m,
                            "raw": m,
                        })
                    return {
                        "connected": True,
                        "count": len(enhanced_models),
                        "models": enhanced_models,
                    }
        except Exception:
            continue
                raw_models = res.json().get("data", [])
                # Enhance models with category tags
                enhanced_models = []
                for m in raw_models:
                    m_id = m.get("id", "")
                    provider = m_id.split("/")[0] if "/" in m_id else "other"
                    is_free = "free" in m_id.lower() or provider in ["oc", "auto"]
                    is_1m = any(term in m_id.lower() for term in ["mimo", "gemini", "deepseek-v4"])
                    enhanced_models.append({
                        "id": m_id,
                        "name": m.get("name") or m_id,
                        "provider": provider,
                        "is_free": is_free,
                        "is_1m": is_1m,
                        "raw": m,
                    })
                return {
                    "connected": True,
                    "count": len(enhanced_models),
                    "models": enhanced_models,
                }
    except Exception as exc:
        pass

    # Curated fallback catalog if gateway is offline or initializing
    fallback_models = [
        {"id": "auto/best-chat", "name": "Auto: Best Chat (Fallback Router)", "provider": "auto", "is_free": True, "is_1m": False},
        {"id": "auto/best-coding", "name": "Auto: Best Coding (Fallback Router)", "provider": "auto", "is_free": True, "is_1m": False},
        {"id": "oc/north-mini-code-free", "name": "North Mini Code Free", "provider": "oc", "is_free": True, "is_1m": False},
        {"id": "oc/mimo-v2.5-free", "name": "Mimo v2.5 Free (1M Context)", "provider": "oc", "is_free": True, "is_1m": True},
        {"id": "oc/nemotron-3-ultra-free", "name": "Nemotron 3 Ultra Free", "provider": "oc", "is_free": True, "is_1m": False},
        {"id": "aug/opus4.8", "name": "Claude Opus 4.8", "provider": "aug", "is_free": False, "is_1m": False},
        {"id": "aug/sonnet5-high", "name": "Claude Sonnet 5 High", "provider": "aug", "is_free": False, "is_1m": False},
        {"id": "tllm/gemini_3_pro", "name": "Gemini 3 Pro (1M Context)", "provider": "tllm", "is_free": False, "is_1m": True},
    ]

    return {
        "connected": False,
        "count": len(fallback_models),
        "models": fallback_models,
        "note": "Gateway currently unreachable; showing default model catalog.",
    }


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """
    Proxy completions to OmniRoute gateway.
    Handles SSE streaming chunks for content and reasoning_content deltas.
    """
    target_base = (req.base_url or os.environ.get("OMNIROUTE_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
    target_key = req.api_key or os.environ.get("OMNIROUTE_API_KEY", DEFAULT_API_KEY)
    target_model = req.model or os.environ.get("OMNIROUTE_MODEL", DEFAULT_MODEL)

    headers = {"Content-Type": "application/json"}
    if target_key:
        headers["Authorization"] = f"Bearer {target_key}"

    # Build messages array including system prompt if provided
    formatted_messages = []
    system_text = req.system_prompt if req.system_prompt is not None else os.environ.get("OMNIROUTE_SYSTEM", "")
    if system_text and system_text.strip():
        formatted_messages.append({"role": "system", "content": system_text.strip()})

    for m in req.messages:
        formatted_messages.append({"role": m.role, "content": m.content})

    payload: Dict[str, Any] = {
        "model": target_model,
        "messages": formatted_messages,
        "stream": req.stream,
        "temperature": req.temperature,
    }
    if req.max_tokens:
        payload["max_tokens"] = req.max_tokens

        async def event_generator():
            start_time = time.time()
            served_model = target_model
            total_usage = {}
            has_error = False

            connected = False
            last_err = ""

            for candidate in candidate_urls(target_base):
                try:
                    timeout = httpx.Timeout(300.0, connect=6.0)
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        async with client.stream(
                            "POST",
                            f"{candidate}/chat/completions",
                            json=payload,
                            headers=headers,
                        ) as response:
                            connected = True
                            if response.status_code >= 400:
                                error_body = await response.aread()
                                try:
                                    err_json = json.loads(error_body.decode(errors="replace"))
                                    err_msg = err_json.get("error", {}).get("message") or str(err_json)
                                except Exception:
                                    err_msg = error_body.decode(errors="replace")[:300] or f"HTTP {response.status_code}"
                                yield f"data: {json.dumps({'type': 'error', 'message': f'Gateway Error ({response.status_code}): {err_msg}'})}\n\n"
                                return

                            buffer = ""
                            async for raw_chunk in response.aiter_bytes():
                                buffer += raw_chunk.decode("utf-8", errors="replace")
                                lines = buffer.split("\n")
                                buffer = lines.pop()  # Keep incomplete line in buffer

                                for line in lines:
                                    line = line.strip()
                                    if not line or not line.startswith("data:"):
                                        continue
                                    raw_data = line[5:].strip()
                                    if raw_data == "[DONE]":
                                        continue
                                    try:
                                        chunk = json.loads(raw_data)
                                    except json.JSONDecodeError:
                                        continue

                                    if chunk.get("model"):
                                        served_model = chunk["model"]
                                    if chunk.get("usage"):
                                        total_usage = chunk["usage"]

                                    choices = chunk.get("choices") or []
                                    if not choices:
                                        continue
                                    delta = choices[0].get("delta") or {}

                                    # 1. Stream reasoning if model is thinking
                                    reasoning_delta = delta.get("reasoning_content")
                                    if reasoning_delta:
                                        yield f"data: {json.dumps({'type': 'reasoning', 'delta': reasoning_delta})}\n\n"

                                    # 2. Stream content piece
                                    content_delta = delta.get("content")
                                    if content_delta:
                                        yield f"data: {json.dumps({'type': 'content', 'delta': content_delta})}\n\n"
                            break  # successfully streamed
                except (httpx.ConnectError, httpx.TimeoutException) as exc:
                    last_err = str(exc)
                    continue
                except Exception as exc:
                    has_error = True
                    yield f"data: {json.dumps({'type': 'error', 'message': f'Unexpected error: {str(exc)}'})}\n\n"
                    break

            if not connected and not has_error:
                has_error = True
                yield f"data: {json.dumps({'type': 'error', 'message': f'Cannot reach OmniRoute gateway at {target_base} ({last_err}). Please check if `omniroute` is running in your terminal.'})}\n\n"

            # Final metadata event
            elapsed = time.time() - start_time
            if not has_error:
                yield f"data: {json.dumps({'type': 'meta', 'model': served_model, 'usage': total_usage, 'latency': round(elapsed, 2)})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming mode
    payload["stream"] = False
    for candidate in candidate_urls(target_base):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                res = await client.post(f"{candidate}/chat/completions", json=payload, headers=headers)
                if res.status_code >= 400:
                    raise HTTPException(status_code=res.status_code, detail=res.text)
                return res.json()
        except (httpx.ConnectError, httpx.TimeoutException):
            continue
    raise HTTPException(
        status_code=503,
        detail=f"Cannot reach OmniRoute gateway at {target_base}.",
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Starting OmniRoute Web Server on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
