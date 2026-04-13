"""
web/app.py — FastAPI 애플리케이션 팩토리
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from web.routes import router

BASE_DIR = Path(__file__).parent


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Code Reviewer",
        description="GitHub 레포지토리 AI 코드 리뷰 서비스",
        version="0.1.0",
    )

    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    app.include_router(router)

    return app
