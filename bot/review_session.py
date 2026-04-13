"""
bot/review_session.py — Discord 리뷰 세션 상태 관리 (인메모리)
"""

from dataclasses import dataclass, field
from pathlib import Path
from agent.code_fixer import FixPlan


@dataclass
class ReviewSession:
    repo_url: str
    owner: str
    repo_name: str
    review_text: str                      # 상세 리뷰 전문 (수정 계획 생성 입력)
    file_contents: dict[str, str]         # {상대경로: 파일내용} — 파일 선택용
    repo_path: Path | None = None         # 로컬 클론 경로
    fix_plan: FixPlan | None = None       # 수정 계획 (생성 후 저장)


# user_id → ReviewSession
_store: dict[int, ReviewSession] = {}


def get(user_id: int) -> ReviewSession | None:
    return _store.get(user_id)


def save(user_id: int, session: ReviewSession) -> None:
    _store[user_id] = session


def clear(user_id: int) -> None:
    session = _store.pop(user_id, None)
    if session and session.repo_path:
        from core.cloner import RepoCloner
        RepoCloner().cleanup(session.repo_path)
