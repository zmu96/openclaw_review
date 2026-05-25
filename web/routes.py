"""
web/routes.py — FastAPI 라우트 정의
"""

import os
from fastapi import APIRouter, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from agent.reviewer import CodeReviewer
from agent.pr_reviewer import PRReviewer
from agent.gemini_client import LLMClient
from core.reporter import Reporter

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
reviewer: CodeReviewer | None = None
reporter: Reporter | None = None
pr_reviewer: PRReviewer | None = None


def _web_llm() -> LLMClient:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("웹 UI를 사용하려면 ANTHROPIC_API_KEY 환경변수를 설정하세요.")
    return LLMClient(api_key=key)


def get_reviewer() -> CodeReviewer:
    global reviewer
    if reviewer is None:
        reviewer = CodeReviewer(llm=_web_llm())
    return reviewer


def get_reporter() -> Reporter:
    global reporter
    if reporter is None:
        reporter = Reporter()
    return reporter


def get_pr_reviewer() -> PRReviewer:
    global pr_reviewer
    if pr_reviewer is None:
        pr_reviewer = PRReviewer(llm=_web_llm())
    return pr_reviewer


@router.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return JSONResponse({"status": "ok"})


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@router.post("/review", response_class=HTMLResponse)
async def run_review(request: Request, repo_url: str = Form(...)):
    try:
        result = await get_reviewer().review(repo_url)
        html_path = get_reporter().save_html(result)
        html_content = html_path.read_text(encoding="utf-8")
        return HTMLResponse(content=html_content)
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"error": str(e)},
            status_code=400,
        )


@router.get("/reports/{filename}")
async def download_report(filename: str):
    path = Path("./reports/output") / filename
    if not path.exists():
        return HTMLResponse("파일을 찾을 수 없습니다.", status_code=404)
    return FileResponse(path)


@router.post("/pr-review", response_class=HTMLResponse)
async def run_pr_review(request: Request, pr_url: str = Form(...)):
    try:
        result = await get_pr_reviewer().review(pr_url)
        return templates.TemplateResponse(
            request,
            "pr_result.html",
            {
                "pr_title": result.pr_title,
                "pr_number": result.pr_number,
                "pr_url": result.pr_url,
                "comment_url": result.comment_url,
                "final_review": result.final_review,
            },
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"error": str(e)},
            status_code=400,
        )
