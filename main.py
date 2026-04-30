from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routers import chat
from logging_config import setup_logging


setup_logging()

_static = Path(__file__).resolve().parent / "static" / "browser"
_serve_spa = _static.joinpath("index.html").is_file()

app = FastAPI(
    docs_url=None if _serve_spa else "/docs",
    redoc_url=None if _serve_spa else "/redoc",
    openapi_url=None if _serve_spa else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(chat.router)

if _serve_spa:
    app.mount("/", StaticFiles(directory=_static, html=True), name="spa")

