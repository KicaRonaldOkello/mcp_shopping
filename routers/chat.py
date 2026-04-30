"""Server-Sent Events (SSE) streaming for the Meridian LangGraph chatbot."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from agents.graph import compile_graph

router = APIRouter(prefix="/api/chat", tags=["chat"])

_graph = None


def get_compiled_graph():
    global _graph
    if _graph is None:
        _graph = compile_graph()
    return _graph


class ChatStreamRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    thread_id: str | None = Field(
        default=None,
        description="Conversation id; omit to start a new thread.",
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _chunk_text(text: str, size: int = 72) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] if text else []


def _ai_texts_from_update(update: dict[str, Any]) -> list[str]:
    msgs = update.get("messages")
    if not msgs:
        return []
    out: list[str] = []
    for m in msgs:
        if isinstance(m, AIMessage) and m.content:
            out.append(str(m.content))
    return out


async def _stream_run(message: str, thread_id: str) -> AsyncIterator[str]:
    yield _sse("meta", {"thread_id": thread_id})

    try:
        graph = get_compiled_graph()
        config = {"configurable": {"thread_id": thread_id}}
        async for chunk in graph.astream(
            {"messages": [HumanMessage(content=message)]},
            config,
            stream_mode="updates",
        ):
            if not isinstance(chunk, dict):
                continue
            for node_name, update in chunk.items():
                if not isinstance(update, dict):
                    continue
                yield _sse("step", {"node": node_name})
                for text in _ai_texts_from_update(update):
                    for part in _chunk_text(text):
                        yield _sse("token", {"text": part})
        yield _sse("done", {})
    except Exception as exc:
        yield _sse("error", {"message": str(exc)})


@router.post("/stream")
async def chat_stream(body: ChatStreamRequest):
    thread_id = body.thread_id or str(uuid.uuid4())

    async def event_source():
        async for line in _stream_run(body.message.strip(), thread_id):
            yield line

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
