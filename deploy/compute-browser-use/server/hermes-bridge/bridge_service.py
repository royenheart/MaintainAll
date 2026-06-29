"""Hermes Bridge — Connects AstrBot messages to Hermes Agent.

This service receives messages forwarded by the AstrBot hermes_forward plugin
and passes them to the Hermes Agent via its HTTP API (run_agent.py in server mode).

Hermes Agent runs in headless mode — without its own gateway. All messages come
through this bridge from AstrBot's multi-platform pipeline.

Environment variables:
    HERMES_AGENT_URL  — Hermes Agent HTTP endpoint (default: http://hermes-agent:8420)
    BRIDGE_PORT       — Bridge service port (default: 8421)
    AUTH_TOKEN        — Optional shared auth token
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger("hermes-bridge")

HERMES_AGENT_URL = os.environ.get("HERMES_AGENT_URL", "http://hermes-api:8420").rstrip("/")
BRIDGE_PORT = int(os.environ.get("BRIDGE_PORT", "8421"))
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")

app = FastAPI(title="Hermes Bridge", version="0.1.0")

# Session tracking: maps AstrBot session_id → Hermes conversation_id
sessions: dict[str, str] = {}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not AUTH_TOKEN:
        return await call_next(request)
    if request.url.path == "/health":
        return await call_next(request)
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if token != AUTH_TOKEN:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    return await call_next(request)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "hermes-bridge", "sessions": len(sessions)}


@app.post("/api/v1/chat")
async def chat(request: Request):
    """Forward a chat message from AstrBot to Hermes Agent.

    Request body:
    {
        "session_id": "unique-session-id",
        "platform": "telegram|discord|qq|...",
        "sender_id": "user-123",
        "sender_name": "John",
        "message": "Hello, can you help me?",
        "attachments": [{"type": "image", "url": "..."}]
    }

    Returns streaming or non-streaming response from Hermes Agent.
    """
    body = await request.json()
    session_id = body.get("session_id", str(uuid.uuid4()))
    message = body.get("message", "")
    sender_id = body.get("sender_id", "unknown")
    sender_name = body.get("sender_name", "User")
    platform = body.get("platform", "unknown")
    streaming = body.get("streaming", False)

    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    # Get or create Hermes conversation
    conv_id = sessions.get(session_id)
    if not conv_id:
        conv_id = str(uuid.uuid4())
        sessions[session_id] = conv_id

    # Build Hermes Agent request
    hermes_payload = {
        "conversation_id": conv_id,
        "message": message,
        "context": {
            "platform": platform,
            "sender_id": sender_id,
            "sender_name": sender_name,
        },
        "stream": streaming,
    }

    logger.info("Forwarding to Hermes: session=%s conv=%s msg=%s...",
                session_id, conv_id, message[:50])

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
        try:
            if streaming:
                # Stream response back
                async def stream_response():
                    async with client.stream(
                        "POST",
                        f"{HERMES_AGENT_URL}/api/v1/chat",
                        json=hermes_payload,
                    ) as resp:
                        resp.raise_for_status()
                        async for chunk in resp.aiter_bytes():
                            yield chunk
                return StreamingResponse(stream_response(), media_type="text/event-stream")
            else:
                resp = await client.post(
                    f"{HERMES_AGENT_URL}/api/v1/chat",
                    json=hermes_payload,
                )
                resp.raise_for_status()
                return resp.json()

        except httpx.HTTPStatusError as e:
            logger.error("Hermes Agent error: %s", e)
            return JSONResponse(
                status_code=502,
                content={"error": f"Hermes Agent returned {e.response.status_code}"},
            )
        except httpx.ConnectError:
            logger.error("Hermes Agent unreachable at %s", HERMES_AGENT_URL)
            return JSONResponse(
                status_code=503,
                content={"error": "Hermes Agent is not available"},
            )


@app.post("/api/v1/chat/stream")
async def chat_stream(request: Request):
    """Streaming chat endpoint."""
    body = await request.json()
    body["streaming"] = True
    # Re-use the chat endpoint with streaming=True
    request._body = json.dumps(body).encode()
    return await chat(request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=BRIDGE_PORT)
