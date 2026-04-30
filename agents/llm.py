"""OpenRouter-backed chat model (default: GPT-4o mini)."""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_APP_TITLE,
    OPENROUTER_HTTP_REFERER,
    OPENROUTER_MODEL,
    OPENROUTER_REASONING_EFFORT,
    OPENROUTER_TEMPERATURE,
)


def _openrouter_model_without_thinking(model: str) -> str:
    """Drop OpenRouter `:thinking` variant so the API uses the non-thinking model id."""
    return model.removesuffix(":thinking")


def get_chat_model() -> ChatOpenAI:
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to .env or export it to use LLM routing."
        )
    model = _openrouter_model_without_thinking(OPENROUTER_MODEL)
    return ChatOpenAI(
        model=model,
        openai_api_key=OPENROUTER_API_KEY,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=OPENROUTER_TEMPERATURE,
        default_headers={"HTTP-Referer": OPENROUTER_HTTP_REFERER, "X-Title": OPENROUTER_APP_TITLE},
        extra_body={
            "reasoning": {
                "effort": OPENROUTER_REASONING_EFFORT,
            }
        },
    )
