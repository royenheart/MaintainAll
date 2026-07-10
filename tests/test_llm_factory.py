from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from MaintainAll.config import Settings
from MaintainAll.graph.llm import build_chat_model


def test_build_chat_model_deepseek():
    settings = Settings(
        api_base="https://api.deepseek.com",
        model="deepseek-v4-flash",
        api_key=SecretStr("sk-test"),
    )
    mock_model = MagicMock()
    mock_model.invoke = MagicMock()

    with patch("langchain_deepseek.ChatDeepSeek", return_value=mock_model) as mock_cls:
        model = build_chat_model(settings)

    mock_cls.assert_called_once_with(
        model="deepseek-v4-flash",
        api_key="sk-test",
        api_base="https://api.deepseek.com/v1",
    )
    assert hasattr(model, "invoke")


def test_build_chat_model_deepseek_with_v1_base():
    settings = Settings(
        api_base="https://api.deepseek.com/v1",
        model="deepseek-v4-flash",
        api_key=SecretStr("sk-test"),
    )
    mock_model = MagicMock()

    with patch("langchain_deepseek.ChatDeepSeek", return_value=mock_model) as mock_cls:
        build_chat_model(settings)

    mock_cls.assert_called_once_with(
        model="deepseek-v4-flash",
        api_key="sk-test",
        api_base="https://api.deepseek.com/v1",
    )


def test_build_chat_model_openai_compatible():
    settings = Settings(
        api_base="https://api.example.com",
        model="gpt-4o-mini",
        api_key=SecretStr("sk-test"),
    )
    mock_model = MagicMock()

    with patch("langchain_openai.ChatOpenAI", return_value=mock_model) as mock_cls:
        model = build_chat_model(settings)

    mock_cls.assert_called_once_with(
        model="gpt-4o-mini",
        api_key="sk-test",
        base_url="https://api.example.com",
    )
    assert hasattr(model, "invoke")


def test_build_chat_model_no_api_key():
    settings = Settings(api_base="https://api.deepseek.com", model="deepseek-v4-flash")
    with pytest.raises(RuntimeError, match="API key not configured"):
        build_chat_model(settings)
