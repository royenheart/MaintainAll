from __future__ import annotations

from MaintainAll.config import Settings


def build_chat_model(settings: Settings):
    key = settings.api_key.get_secret_value() if settings.api_key else None
    if not key:
        raise RuntimeError("API key not configured")
    base = settings.api_base.rstrip("/")
    if "deepseek.com" in base:
        from langchain_deepseek import ChatDeepSeek

        return ChatDeepSeek(
            model=settings.model,
            api_key=key,
            api_base=base if base.endswith("/v1") else base + "/v1",
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=settings.model, api_key=key, base_url=base)
