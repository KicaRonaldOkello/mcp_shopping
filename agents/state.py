from __future__ import annotations

from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from agents.agents import RouterTarget, SpecialistAgentName


class OrderItem(TypedDict):
    sku: str
    quantity: int


class MeridianState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]

    guardrail_ok: NotRequired[bool]
    blocked_reason: NotRequired[str | None]

    route: NotRequired[Literal["product", "account"] | None]
    router_target: NotRequired[RouterTarget | None]
    requested_agent: NotRequired[SpecialistAgentName | None]

    session_verified: NotRequired[bool]
    customer_id: NotRequired[str | None]

    selected_sku: NotRequired[str | None]
    order_id: NotRequired[str | None]
    pending_order_items: NotRequired[list[OrderItem]]

    last_tool_name: NotRequired[str | None]
    last_tool_result: NotRequired[dict | list | str | None]
