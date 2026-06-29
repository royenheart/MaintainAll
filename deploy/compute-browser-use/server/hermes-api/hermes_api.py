"""Hermes Agent HTTP API Wrapper.

Wraps Hermes Agent's `run_agent.AIAgent` in a FastAPI HTTP service.

Startup: Always starts the HTTP server, even without an API key.
Chat: If no valid API key is configured, returns a clear error instructing
      the user how to configure it via .env or docker compose environment.

Supported models: 37 providers including Anthropic, OpenAI, Google Gemini,
DeepSeek, OpenRouter, xAI, Qwen, Ollama, and many more.
See: https://github.com/NousResearch/hermes-agent

Environment:
    ANTHROPIC_API_KEY / OPENAI_API_KEY — LLM credentials
    HERMES_CONFIG — path to hermes config.yaml
    HERMES_HOME  — hermes data directory
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger("hermes-api")

HERMES_SRC = os.environ.get("HERMES_SRC", "/opt/hermes-agent")
if HERMES_SRC not in sys.path:
    sys.path.insert(0, HERMES_SRC)

app = FastAPI(title="Hermes Agent API", version="0.1.0")

_executor = ThreadPoolExecutor(max_workers=4)
_conversations: dict[str, list[dict]] = {}
_agent = None
_agent_lock = asyncio.Lock()
_agent_error: Optional[str] = None


def _get_api_key() -> str:
    """Get API key from environment. Returns empty string if not set."""
    return os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY", "")


def _detect_provider() -> tuple[str, str]:
    """Detect provider and model from environment keys."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", os.environ.get("HERMES_MODEL", "claude-sonnet-4-20250514")
    if os.environ.get("OPENAI_API_KEY"):
        base = os.environ.get("OPENAI_BASE_URL", "")
        if base and ("openrouter" in base.lower()):
            return "openrouter", os.environ.get("HERMES_MODEL", "")
        return "openai", os.environ.get("HERMES_MODEL", "gpt-4o")
    return "", ""


def _build_agent():
    """Build a Hermes AIAgent instance. Returns (agent, None) or (None, error_msg)."""
    global _agent_error

    from run_agent import AIAgent

    api_key = _get_api_key()
    if not api_key:
        _agent_error = (
            "No LLM API key configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY "
            "in .env or docker-compose environment, then restart this service.\n"
            "Example: ANTHROPIC_API_KEY=sk-ant-...\n"
            "See docker-compose.yml environment section."
        )
        logger.warning(_agent_error)
        return None

    provider, model = _detect_provider()
    logger.info("Building Hermes Agent: provider=%s model=%s", provider, model)

    enabled_toolsets = ["computer_use", "web_search", "file_operations"]
    disabled_toolsets = ["terminal", "browser"]

    try:
        agent = AIAgent(
            api_key=api_key,
            provider=provider,
            model=model,
            max_iterations=int(os.environ.get("HERMES_MAX_ITERATIONS", "30")),
            enabled_toolsets=enabled_toolsets,
            disabled_toolsets=disabled_toolsets,
            platform="astrbot",
            skip_memory=False,
            load_soul_identity=False,
            quiet_mode=True,
        )
        _agent_error = None
        return agent
    except Exception as e:
        _agent_error = f"Failed to initialize Hermes Agent: {e}"
        logger.error(_agent_error)
        return None


async def _get_agent():
    global _agent, _agent_error
    if _agent is None and _agent_error is None:
        async with _agent_lock:
            if _agent is None and _agent_error is None:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(_executor, _build_agent)
                if result is not None:
                    _agent = result
    return _agent


@app.get("/health")
async def health():
    status = "ok"
    details = {"service": "hermes-api"}

    if _agent_error:
        details["agent_status"] = "unconfigured"
        details["agent_error"] = _agent_error[:200]
    elif _agent is not None:
        details["agent_status"] = "ready"
    else:
        details["agent_status"] = "initializing"

    return {"status": status, **details}


@app.post("/api/v1/chat")
async def chat(request: Request):
    body = await request.json()
    message = body.get("message", "")
    conv_id = body.get("conversation_id", str(uuid.uuid4()))
    stream = body.get("stream", False)

    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    # Check: do we have an agent?
    if _agent_error and _agent is None:
        raise HTTPException(
            status_code=503,
            detail=f"Hermes Agent is not configured. {_agent_error[:200]}",
        )

    try:
        agent = await _get_agent()
        if agent is None:
            raise HTTPException(
                status_code=503,
                detail="Hermes Agent is initializing or failed to start. "
                       "Check server logs for details.",
            )

        history = _conversations.get(conv_id, [])
        loop = asyncio.get_running_loop()

        if stream:
            chunks = []

            def stream_cb(text: str):
                chunks.append(text)

            def _run():
                return agent.run_conversation(
                    user_message=message,
                    conversation_history=history if history else None,
                    stream_callback=stream_cb,
                )

            result = await loop.run_in_executor(_executor, _run)
            final_response = result.get("final_response", "")
            if not chunks:
                chunks.append(final_response)

            return {
                "conversation_id": conv_id,
                "reply": final_response,
                "stream_chunks": chunks,
            }
        else:
            def _run():
                return agent.chat(message)

            reply = await loop.run_in_executor(_executor, _run)

            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": reply})
            if len(history) > 40:
                history = history[-40:]
            _conversations[conv_id] = history

            return {"conversation_id": conv_id, "reply": reply}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Hermes Agent error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")


@app.delete("/api/v1/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    _conversations.pop(conv_id, None)
    return {"status": "deleted", "conversation_id": conv_id}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("HERMES_API_PORT", "8420"))
    uvicorn.run(app, host="0.0.0.0", port=port)
