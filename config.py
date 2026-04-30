import os

from dotenv import load_dotenv

load_dotenv()


MCP_SERVER_URL = os.getenv(
    "MCP_SERVER_URL",
    "",
)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_REASONING_EFFORT = os.getenv("OPENROUTER_REASONING_EFFORT", "none")
OPENROUTER_HTTP_REFERER = os.getenv(
    "OPENROUTER_HTTP_REFERER",
    "http://localhost:8000",
)
OPENROUTER_APP_TITLE = os.getenv("OPENROUTER_APP_TITLE", "Meridian support")
OPENROUTER_TEMPERATURE = float(os.getenv("OPENROUTER_TEMPERATURE", "0.2"))
