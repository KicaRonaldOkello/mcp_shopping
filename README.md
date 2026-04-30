---
title: Meridian LangGraph Chat
emoji: 🧭
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
---

FastAPI + LangGraph chat with an Angular SPA in the same Docker image (`runtime-full`). **The YAML block above must stay at the very top of this file** — Hugging Face Spaces reads it for `sdk: docker` and routing to port `8000` (same as `uvicorn` in the `Dockerfile`).

## Hugging Face Spaces

1. [Create a Space](https://huggingface.co/new-space) with SDK **Docker**, or push this repo to an existing Space.
2. **Settings → Secrets:** `OPENROUTER_API_KEY`, `OPENROUTER_HTTP_REFERER` (your Space URL), and optionally `MCP_SERVER_URL`.
3. Health check: `/api/health`.

## Agent flow

```mermaid
flowchart TD
    START([User message]) --> WELCOME[Welcome + guardrail agent]

    WELCOME -->|unsafe / off-topic / policy violation| BLOCK[Refuse / clarify / end turn]
    WELCOME -->|safe + proceed| ROUTE{Route intent}

    ROUTE -->|browse or ask about products| PRODUCT[Product agent]
    ROUTE -->|account / orders / who am I| NEED_AUTH{Session verified?}

    PRODUCT -->|list / search / product detail| PRODUCT
    PRODUCT -->|user commits to purchase| NEED_AUTH2{Session verified?}

    NEED_AUTH -->|no| AUTH[Auth agent<br/>email + PIN]
    NEED_AUTH -->|yes| VERIFIED[Verified user capabilities]

    NEED_AUTH2 -->|no| AUTH
    NEED_AUTH2 -->|yes| ORDER_FLOW[Order agent<br/>create order]

    AUTH -->|verification failed| AUTH
    AUTH -->|verification success| VERIFIED

    VERIFIED --> CHOOSE{User request?}
    CHOOSE -->|customer profile| CUST[Get customer info<br/>MCP tool]
    CHOOSE -->|single order| GET_ORD[Get order<br/>MCP tool]
    CHOOSE -->|order history| LIST_ORD[List orders<br/>MCP tool]
    CHOOSE -->|place new order| ORDER_FLOW

    ORDER_FLOW --> DONE([Assistant reply + updated state])
    CUST --> DONE
    GET_ORD --> DONE
    LIST_ORD --> DONE
    BLOCK --> DONE
    PRODUCT -->|no purchase yet| DONE

    style WELCOME fill:#e8f4f8
    style PRODUCT fill:#e8f8e8
    style AUTH fill:#fff4e6
    style VERIFIED fill:#f0e8ff
    style ORDER_FLOW fill:#ffe8e8
```
