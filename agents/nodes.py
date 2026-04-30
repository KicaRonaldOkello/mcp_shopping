"""LLM-driven routing and specialist agents for Meridian workflows."""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from agents.agents import AGENTS, AgentDefinition, WELCOME_ROUTER_SYSTEM, SpecialistAgentName
from agents.llm import get_chat_model
from agents.llm_router_schema import WelcomeRouter
from agents.state import MeridianState
from agents.tools import load_mcp_tools_for

logger = logging.getLogger(__name__)


def _latest_user_text(state: MeridianState) -> str:
    for message in reversed(state.get("messages") or []):
        if isinstance(message, HumanMessage):
            return str(message.content).strip()
    return ""


_MAX_ROUTER_TURN_CHARS = 700
_MAX_ROUTER_TURNS = 12


def _recent_dialog_for_router(state: MeridianState) -> str:
    """Chronological tail of Human/AIMessage so short replies route with context."""
    lines: list[str] = []
    for message in (state.get("messages") or [])[-_MAX_ROUTER_TURNS:]:
        if isinstance(message, HumanMessage):
            role = "User"
        elif isinstance(message, AIMessage):
            role = "Assistant"
        else:
            continue
        raw = message.content
        content = str(raw).strip() if raw else ""
        if not content:
            continue
        if len(content) > _MAX_ROUTER_TURN_CHARS:
            content = content[: _MAX_ROUTER_TURN_CHARS - 3] + "..."
        lines.append(f"{role}: {content}")
    if not lines:
        return "(no prior turns in this thread)"
    return "\n".join(lines)


_ORDER_CONFIRM_SNIPPETS = (
    "confirm the order",
    "confirm your order",
    "would you like to confirm",
    "place the order",
    "place your order",
    "complete the order",
    "proceed with your order",
    "go ahead with your order",
)


def _looks_like_order_confirmation_prompt(assistant_text: str) -> bool:
    t = assistant_text.lower()
    if any(s in t for s in _ORDER_CONFIRM_SNIPPETS):
        return True
    return "confirm" in t and "order" in t


def _short_affirmative_order_confirmation(state: MeridianState) -> bool:
    """Bypass LLM router when user affirms after assistant asked to confirm an order."""
    if not state.get("session_verified"):
        return False
    user = _latest_user_text(state).strip().lower()
    if not user or len(user) > 140:
        return False
    affirm = (
        "yes",
        "yeah",
        "yep",
        "yup",
        "sure",
        "ok",
        "okay",
        "please",
        "confirm",
        "confirmed",
        "absolutely",
        "definitely",
        "go ahead",
        "proceed",
    )
    if not any(a in user for a in affirm):
        return False
    msgs = state.get("messages") or []
    it = iter(reversed(msgs))
    for m in it:
        if isinstance(m, HumanMessage):
            break
    for m in it:
        if isinstance(m, ToolMessage):
            continue
        if isinstance(m, AIMessage):
            return _looks_like_order_confirmation_prompt(str(m.content or ""))
        if isinstance(m, HumanMessage):
            break
    return False


def _session_snapshot(state: MeridianState) -> str:
    snap = {
        "session_verified": state.get("session_verified", False),
        "customer_id": state.get("customer_id"),
        "selected_sku": state.get("selected_sku"),
        "pending_order_items": state.get("pending_order_items"),
        "order_id": state.get("order_id"),
        "requested_agent": state.get("requested_agent"),
    }
    return json.dumps(snap, default=str)


def _specialist_session_prompt(state: MeridianState, agent_name: SpecialistAgentName) -> str:
    ctx = {
        "session_verified": state.get("session_verified"),
        "customer_id": state.get("customer_id"),
        "selected_sku": state.get("selected_sku"),
        "pending_order_items": state.get("pending_order_items"),
        "order_id": state.get("order_id"),
        "requested_agent": state.get("requested_agent"),
    }
    return (
        f"You are handling the `{agent_name}` workflow.\n"
        "Session context (JSON):\n"
        f"{json.dumps(ctx, default=str)}\n\n"
        "Treat session context as authoritative. If session_verified is true, the customer is "
        "already verified for this thread and you must not ask them to verify again. If "
        "customer_id is present, use it as the verified customer identity.\n\n"
        "Use only the provided tools and return a concise customer-facing answer."
    )


def _tool_message_payload(message: ToolMessage) -> dict[str, Any]:
    raw = message.content
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}
        return parsed if isinstance(parsed, dict) else {"raw": parsed}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        merged: dict[str, Any] = {}
        text_chunks: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                merged.update(item)
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    text_chunks.append(text.strip())
            elif isinstance(item, str) and item.strip():
                text_chunks.append(item.strip())
        if text_chunks and "raw_text" not in merged:
            merged["raw_text"] = "\n".join(text_chunks)
        return merged
    return {}


def _deep_get(mapping: Any, *path: str) -> Any:
    cur = mapping
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _looks_verified(payload: dict[str, Any]) -> bool:
    verdicts = (
        payload.get("verified"),
        payload.get("success"),
        payload.get("is_verified"),
        payload.get("authenticated"),
        _deep_get(payload, "customer", "verified"),
        _deep_get(payload, "result", "verified"),
        _deep_get(payload, "data", "verified"),
    )
    return any(v is True for v in verdicts)


def _normalize_uuid(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return str(UUID(text))
    except (ValueError, TypeError, AttributeError):
        return None


def _extract_customer_id(payload: dict[str, Any]) -> str | None:
    candidates = (
        payload.get("customer_id"),
        _deep_get(payload, "customer", "id"),
        _deep_get(payload, "result", "customer_id"),
        _deep_get(payload, "result", "customer", "id"),
        _deep_get(payload, "data", "customer_id"),
        _deep_get(payload, "data", "customer", "id"),
    )
    for value in candidates:
        normalized = _normalize_uuid(value)
        if normalized is not None:
            return normalized
    return None


def _patch_from_verify_tool_messages(new_messages: list[Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for message in reversed(new_messages):
        if not isinstance(message, ToolMessage):
            continue
        if (getattr(message, "name", "") or "") != "verify_customer_pin":
            continue

        payload = _tool_message_payload(message)
        customer_id = _extract_customer_id(payload)
        verified = _looks_verified(payload) or customer_id is not None

        patch["session_verified"] = verified
        if verified and customer_id is not None:
            patch["customer_id"] = customer_id
        elif not verified:
            patch["customer_id"] = None
        break
    return patch


_REACT_AGENTS: dict[SpecialistAgentName, Any] = {}
_INIT_LOCK = asyncio.Lock()


async def _build_react_agent(
    name: SpecialistAgentName,
    definition: AgentDefinition,
    llm: Any,
) -> tuple[SpecialistAgentName, Any]:
    tools = await load_mcp_tools_for(definition.tool_group)
    agent = create_react_agent(
        llm,
        tools,
        prompt=definition.system_prompt,
        name=f"{name}_react",
    )
    return name, agent


async def _ensure_agents() -> None:
    if _REACT_AGENTS:
        return
    async with _INIT_LOCK:
        if _REACT_AGENTS:
            return
        llm = get_chat_model()
        pairs = await asyncio.gather(
            *(
                _build_react_agent(name, definition, llm)
                for name, definition in AGENTS.items()
            )
        )
        for name, agent in pairs:
            _REACT_AGENTS[name] = agent


async def block_reply(_: MeridianState) -> MeridianState:
    return {}


async def welcome_llm_router(state: MeridianState) -> MeridianState:
    await _ensure_agents()

    if _short_affirmative_order_confirmation(state):
        return {
            "guardrail_ok": True,
            "router_target": "create_order",
            "requested_agent": "create_order",
            "route": "account",
        }

    llm = get_chat_model()
    structured = llm.with_structured_output(WelcomeRouter)
    decision: WelcomeRouter = await structured.ainvoke(
        [
            SystemMessage(
                content=WELCOME_ROUTER_SYSTEM.format(
                    session_json=_session_snapshot(state),
                    recent_dialog=_recent_dialog_for_router(state),
                )
            ),
            HumanMessage(content=_latest_user_text(state) or "(empty message)"),
        ]
    )

    if not decision.safe_to_proceed or decision.next_agent == "block":
        return {
            "guardrail_ok": False,
            "blocked_reason": "llm_router_block",
            "router_target": "block",
            "messages": [
                AIMessage(content=decision.block_message or "I can’t help with that request.")
            ],
        }

    target = decision.next_agent
    requested_agent = decision.requested_agent
    if target != "auth":
        requested_agent = target

    out: MeridianState = {
        "guardrail_ok": True,
        "router_target": target,
        "requested_agent": requested_agent,
        "route": "account" if target != "product" else "product",
    }
    if decision.brief_assistant_note:
        out["messages"] = [AIMessage(content=decision.brief_assistant_note)]
    return out


async def _invoke_specialist(agent_name: SpecialistAgentName, state: MeridianState) -> MeridianState:
    await _ensure_agents()
    base_messages = [
        SystemMessage(content=_specialist_session_prompt(state, agent_name)),
        *list(state.get("messages") or []),
    ]
    before = len(base_messages)
    agent = _REACT_AGENTS[agent_name]
    try:
        out = await agent.ainvoke({"messages": base_messages}, config={"recursion_limit": 40})
    except Exception as exc:
        logger.exception("LLM specialist failed", extra={"agent": agent_name})
        return {"messages": [AIMessage(content=f"{agent_name} assistant error: {exc}")]}

    messages = out.get("messages") or []
    tail = messages[before:] if len(messages) >= before else messages
    return {"messages": tail}


async def product_llm_agent(state: MeridianState) -> MeridianState:
    return await _invoke_specialist("product", state)


async def auth_llm_agent(state: MeridianState) -> MeridianState:
    result = await _invoke_specialist("auth", state)
    tool_patch = _patch_from_verify_tool_messages(result.get("messages") or [])
    if tool_patch.get("session_verified") and state.get("requested_agent") == "auth":
        tool_patch["requested_agent"] = None
    return {**result, **tool_patch}


async def customer_llm_agent(state: MeridianState) -> MeridianState:
    return await _invoke_specialist("customer", state)


async def get_order_llm_agent(state: MeridianState) -> MeridianState:
    return await _invoke_specialist("get_order", state)


async def list_orders_llm_agent(state: MeridianState) -> MeridianState:
    return await _invoke_specialist("list_orders", state)


async def create_order_llm_agent(state: MeridianState) -> MeridianState:
    return await _invoke_specialist("create_order", state)


__all__ = [
    "auth_llm_agent",
    "block_reply",
    "create_order_llm_agent",
    "customer_llm_agent",
    "get_order_llm_agent",
    "list_orders_llm_agent",
    "product_llm_agent",
    "welcome_llm_router",
]
