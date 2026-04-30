from __future__ import annotations

import asyncio
import logging
from typing import Literal

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from config import MCP_SERVER_URL

logger = logging.getLogger(__name__)

MCP_SERVER_NAME = "order"

_all_mcp_tools: list[BaseTool] | None = None
_mcp_tools_lock = asyncio.Lock()

PRODUCT_TOOL_NAMES: frozenset[str] = frozenset(
    {"list_products", "get_product", "search_products"}
)
AUTH_TOOL_NAMES: frozenset[str] = frozenset({"verify_customer_pin"})
CUSTOMER_TOOL_NAMES: frozenset[str] = frozenset({"get_customer"})
GET_ORDER_TOOL_NAMES: frozenset[str] = frozenset({"get_order"})
LIST_ORDERS_TOOL_NAMES: frozenset[str] = frozenset({"list_orders"})
CREATE_ORDER_TOOL_NAMES: frozenset[str] = frozenset({"create_order"})

MeridianToolAgent = Literal[
    "product",
    "auth",
    "customer",
    "get_order",
    "list_orders",
    "create_order",
]


def order_mcp_url() -> str:
    return MCP_SERVER_URL


def _client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            MCP_SERVER_NAME: {
                "url": order_mcp_url(),
                "transport": "streamable_http",
            }
        }
    )


async def _get_all_mcp_tools() -> list[BaseTool]:
    """Single MCP list-tools round trip; reused for every specialist agent."""
    global _all_mcp_tools
    if _all_mcp_tools is not None:
        return _all_mcp_tools
    async with _mcp_tools_lock:
        if _all_mcp_tools is not None:
            return _all_mcp_tools
        client = _client()
        _all_mcp_tools = await client.get_tools(server_name=MCP_SERVER_NAME)
        logger.info(
            "Loaded %d tools from MCP server %s",
            len(_all_mcp_tools),
            MCP_SERVER_NAME,
        )
        return _all_mcp_tools


def _filter_tools(all_tools: list[BaseTool], names: frozenset[str]) -> list[BaseTool]:
    by_name = {t.name: t for t in all_tools}
    missing = names - by_name.keys()
    if missing:
        raise RuntimeError(
            f"MCP server missing expected tools: {sorted(missing)}. "
            f"Available: {sorted(by_name.keys())}"
        )
    return [by_name[n] for n in sorted(names)]


async def load_mcp_tools_for(agent: MeridianToolAgent) -> list[BaseTool]:
    sets: dict[MeridianToolAgent, frozenset[str]] = {
        "product": PRODUCT_TOOL_NAMES,
        "auth": AUTH_TOOL_NAMES,
        "customer": CUSTOMER_TOOL_NAMES,
        "get_order": GET_ORDER_TOOL_NAMES,
        "list_orders": LIST_ORDERS_TOOL_NAMES,
        "create_order": CREATE_ORDER_TOOL_NAMES,
    }
    names = sets[agent]
    all_tools = await _get_all_mcp_tools()
    return _filter_tools(all_tools, names)
