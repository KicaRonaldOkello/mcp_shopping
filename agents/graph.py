from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agents.llm import get_chat_model
from agents.nodes import (
    auth_llm_agent,
    block_reply,
    create_order_llm_agent,
    customer_llm_agent,
    get_order_llm_agent,
    list_orders_llm_agent,
    product_llm_agent,
    welcome_llm_router,
)
from agents.state import MeridianState

NODE_WELCOME = "welcome_llm"
NODE_BLOCK = "block_reply"
NODE_PRODUCT = "product_llm"
NODE_AUTH = "auth_llm"
NODE_CUSTOMER = "customer_llm"
NODE_GET_ORDER = "get_order_llm"
NODE_LIST_ORDERS = "list_orders_llm"
NODE_CREATE_ORDER = "create_order_llm"


def route_after_welcome(state: MeridianState) -> str:
    if not state.get("guardrail_ok", False):
        return NODE_BLOCK

    routes = {
        "product": NODE_PRODUCT,
        "auth": NODE_AUTH,
        "customer": NODE_CUSTOMER,
        "get_order": NODE_GET_ORDER,
        "list_orders": NODE_LIST_ORDERS,
        "create_order": NODE_CREATE_ORDER,
        "block": NODE_BLOCK,
    }
    return routes.get(state.get("router_target") or "product", NODE_PRODUCT)


def route_after_auth(state: MeridianState) -> str:
    if not state.get("session_verified"):
        return END

    routes = {
        "product": NODE_PRODUCT,
        "customer": NODE_CUSTOMER,
        "get_order": NODE_GET_ORDER,
        "list_orders": NODE_LIST_ORDERS,
        "create_order": NODE_CREATE_ORDER,
    }
    return routes.get(state.get("requested_agent") or "customer", END)


def build_graph():
    graph = StateGraph(MeridianState)

    graph.add_node(NODE_WELCOME, welcome_llm_router)
    graph.add_node(NODE_BLOCK, block_reply)
    graph.add_node(NODE_PRODUCT, product_llm_agent)
    graph.add_node(NODE_AUTH, auth_llm_agent)
    graph.add_node(NODE_CUSTOMER, customer_llm_agent)
    graph.add_node(NODE_GET_ORDER, get_order_llm_agent)
    graph.add_node(NODE_LIST_ORDERS, list_orders_llm_agent)
    graph.add_node(NODE_CREATE_ORDER, create_order_llm_agent)

    graph.add_edge(START, NODE_WELCOME)
    graph.add_conditional_edges(
        NODE_WELCOME,
        route_after_welcome,
        {
            NODE_BLOCK: NODE_BLOCK,
            NODE_PRODUCT: NODE_PRODUCT,
            NODE_AUTH: NODE_AUTH,
            NODE_CUSTOMER: NODE_CUSTOMER,
            NODE_GET_ORDER: NODE_GET_ORDER,
            NODE_LIST_ORDERS: NODE_LIST_ORDERS,
            NODE_CREATE_ORDER: NODE_CREATE_ORDER,
        },
    )
    graph.add_edge(NODE_BLOCK, END)
    graph.add_edge(NODE_PRODUCT, END)
    graph.add_conditional_edges(
        NODE_AUTH,
        route_after_auth,
        {
            NODE_PRODUCT: NODE_PRODUCT,
            NODE_CUSTOMER: NODE_CUSTOMER,
            NODE_GET_ORDER: NODE_GET_ORDER,
            NODE_LIST_ORDERS: NODE_LIST_ORDERS,
            NODE_CREATE_ORDER: NODE_CREATE_ORDER,
            END: END,
        },
    )
    graph.add_edge(NODE_CUSTOMER, END)
    graph.add_edge(NODE_GET_ORDER, END)
    graph.add_edge(NODE_LIST_ORDERS, END)
    graph.add_edge(NODE_CREATE_ORDER, END)

    return graph


def compile_graph():
    from langgraph.checkpoint.memory import MemorySaver

    try:
        get_chat_model()
    except RuntimeError as exc:
        raise RuntimeError(
            "The Meridian agent graph requires OPENROUTER_API_KEY. "
            "Set it in .env before using the chat workflow."
        ) from exc

    return build_graph().compile(checkpointer=MemorySaver())
