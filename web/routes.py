"""
web/routes.py — FastAPI 라우트 정의
"""

import os
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from agent.reviewer import CodeReviewer
from agent.pr_reviewer import PRReviewer
from agent.code_fixer import CodeFixer
from agent.gemini_client import LLMClient
from core.git_ops import GitHubOps
from core.reporter import Reporter
import web.web_session as web_session

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
_reporter: Reporter | None = None


# ── 내부 헬퍼 ────────────────────────────────────────────────────


def get_reporter() -> Reporter:
    global _reporter
    if _reporter is None:
        _reporter = Reporter()
    return _reporter


def _parse_github_url(url: str) -> tuple[str, str] | None:
    """GitHub URL에서 (owner, repo) 추출. 실패 시 None."""
    m = re.match(r"https?://github\.com/([^/]+)/([^/?\s#]+)", url)
    if not m:
        return None
    return m.group(1), m.group(2).removesuffix(".git")


def _parse_card(text: str) -> dict[str, str]:
    """final_summary의 DISCORD_CARD 섹션에서 key: value 파싱."""
    m = re.search(
        r'(?:##\s*)?DISCORD_CARD\s*\n([\s\S]*?)(?=\n(?:##\s*)?상세 리뷰|\n##\s|\Z)',
        text,
    )
    if not m:
        return {}
    card: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            card[key.strip()] = val.strip()
    return card


# ── 요청 바디 모델 ────────────────────────────────────────────────


class SessionRequest(BaseModel):
    session_id: str


class ReplanRequest(BaseModel):
    session_id: str
    feedback: str


# ── 페이지 라우트 ─────────────────────────────────────────────────


@router.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return JSONResponse({"status": "ok"})


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@router.post("/review", response_class=HTMLResponse)
async def run_review(
    request: Request,
    repo_url: str = Form(...),
    api_key: str = Form(...),
):
    try:
        # URL 유효성 검증
        parsed = _parse_github_url(repo_url)
        if not parsed:
            return templates.TemplateResponse(
                request,
                "index.html",
                {"error": "올바른 GitHub URL을 입력해 주세요. (예: https://github.com/user/repo)"},
                status_code=400,
            )
        owner, repo_name = parsed

        # API 키 형식 검증
        api_key = api_key.strip()
        if not api_key.startswith("sk-ant-"):
            return templates.TemplateResponse(
                request,
                "index.html",
                {"error": "올바른 Anthropic API 키 형식이 아닙니다. (sk-ant-... 형식)"},
                status_code=400,
            )

        # API 키 유효성 검증 (실제 API 호출)
        llm = LLMClient(api_key=api_key)
        ok, err = await llm.validate()
        if not ok:
            return templates.TemplateResponse(
                request,
                "index.html",
                {"error": f"API 키 검증 실패: {err}"},
                status_code=400,
            )

        # 리뷰 실행
        reviewer = CodeReviewer(llm=llm)
        result = await reviewer.review(repo_url)

        # 수정 계획 생성 입력용 리뷰 전문 합본
        review_text = "\n\n---\n\n".join(
            [result.structure_review] + result.chunk_reviews + [result.final_summary]
        )

        # 세션 생성 (api_key 암호화 저장, repo_path cleanup은 세션 종료 시 처리)
        session = web_session.create(
            repo_url=repo_url,
            owner=owner,
            repo_name=repo_name,
            review_text=review_text,
            file_contents=result.file_contents,
            api_key=api_key,
            repo_path=result.repo_path,
        )

        # HTML 보고서 저장 (다운로드 링크용)
        report_path = get_reporter().save_html(result)

        return templates.TemplateResponse(
            request,
            "review_result.html",
            {
                "session_id": session.session_id,
                "repo_url": repo_url,
                "repo_name": result.repo_name,
                "card": _parse_card(result.final_summary),
                "structure_review": result.structure_review,
                "chunk_reviews": result.chunk_reviews,
                "final_summary": result.final_summary,
                "report_filename": report_path.name,
            },
        )
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
async def run_pr_review(
    request: Request,
    pr_url: str = Form(...),
    github_token: str = Form(...),
):
    github_token = github_token.strip()

    # GitHub 토큰 형식 검증
    if not (github_token.startswith("ghp_") or github_token.startswith("github_pat_")):
        return templates.TemplateResponse(
            request,
            "index.html",
            {"error": "올바른 GitHub Token 형식이 아닙니다. (ghp_... 또는 github_pat_... 형식)"},
            status_code=400,
        )

    try:
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_key:
            return templates.TemplateResponse(
                request,
                "index.html",
                {"error": "PR 리뷰 기능은 서버에 ANTHROPIC_API_KEY 환경변수가 필요합니다."},
                status_code=400,
            )

        # PRReviewer가 GITHUB_TOKEN 환경변수를 읽으므로 임시 설정 후 즉시 복구
        _prev_token = os.environ.get("GITHUB_TOKEN")
        os.environ["GITHUB_TOKEN"] = github_token
        del github_token  # 로컬 참조 즉시 제거

        try:
            pr_reviewer = PRReviewer(llm=LLMClient(api_key=anthropic_key))
            result = await pr_reviewer.review(pr_url)
        finally:
            # 성공/실패 무관하게 환경변수에서 토큰 즉시 삭제
            if _prev_token is not None:
                os.environ["GITHUB_TOKEN"] = _prev_token
            else:
                os.environ.pop("GITHUB_TOKEN", None)

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


# ── JSON API ──────────────────────────────────────────────────────


@router.post("/api/fix-plan")
async def api_fix_plan(body: SessionRequest):
    session = web_session.get(body.session_id)
    if not session:
        return JSONResponse({"error": "세션이 만료되었습니다."}, status_code=404)
    try:
        # 이미 생성된 fix_plan이 있으면 재사용 (다시 계획해줘 후 승인 시)
        if session.fix_plan:
            plan = session.fix_plan
        else:
            api_key = web_session.get_api_key(body.session_id)
            fixer = CodeFixer(llm=LLMClient(api_key=api_key))
            plan = await fixer.generate_fix_plan(session.review_text, session.file_contents)
            session.fix_plan = plan
            web_session.save(session)
        return JSONResponse({
            "summary": plan.summary,
            "affected_files": plan.affected_files,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/replan")
async def api_replan(body: ReplanRequest):
    session = web_session.get(body.session_id)
    if not session:
        return JSONResponse({"error": "세션이 만료되었습니다."}, status_code=404)
    try:
        api_key = web_session.get_api_key(body.session_id)
        fixer = CodeFixer(llm=LLMClient(api_key=api_key))
        plan = await fixer.generate_fix_plan(
            session.review_text,
            session.file_contents,
            user_feedback=body.feedback,
        )
        session.fix_plan = plan
        web_session.save(session)
        return JSONResponse({
            "summary": plan.summary,
            "affected_files": plan.affected_files,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/create-pr")
async def api_create_pr(body: SessionRequest):
    session = web_session.get(body.session_id)
    if not session:
        return JSONResponse({"error": "세션이 만료되었습니다."}, status_code=404)
    if not session.fix_plan:
        return JSONResponse({"error": "수정 계획이 없습니다."}, status_code=400)

    try:
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            return JSONResponse(
                {"error": "GITHUB_TOKEN 환경변수가 설정되지 않았습니다."},
                status_code=500,
            )
        if not session.repo_path or not session.repo_path.exists():
            return JSONResponse(
                {"error": "로컬 클론이 존재하지 않습니다. 리뷰를 다시 실행하세요."},
                status_code=400,
            )

        branch_name = f"PRism/{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        pr_body = (
            "## 🤖 PRism 자동 코드 리뷰 수정\n\n"
            f"### 수정 내용\n{session.fix_plan.summary}\n\n"
            "### 수정 파일\n"
            + "\n".join(f"- `{f}`" for f in session.fix_plan.affected_files)
            + "\n\n*이 PR은 PRism AI 코드 리뷰어가 자동 생성했습니다.*"
        )

        git_ops = GitHubOps(github_token)
        pr_url = await git_ops.apply_and_create_pr(
            repo_path=session.repo_path,
            owner=session.owner,
            repo=session.repo_name,
            patches=session.fix_plan.patches,
            branch_name=branch_name,
            pr_title=f"[PRism] 자동 코드 리뷰 수정 ({datetime.now().strftime('%Y-%m-%d')})",
            pr_body=pr_body,
        )
        return JSONResponse({"pr_url": pr_url})

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    finally:
        # 성공/실패 모두 세션 정리 및 로컬 클론 삭제
        web_session.clear(body.session_id)


@router.post("/api/close-session")
async def api_close_session(body: SessionRequest):
    """리뷰만 보기 / 거절 시 세션 정리."""
    web_session.clear(body.session_id)
    return JSONResponse({"ok": True})
