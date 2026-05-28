"""
web/web_session.py — 웹 UI용 UUID 기반 인메모리 세션 스토어
"""

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet

from agent.code_fixer import FixPlan


def _init_fernet() -> Fernet:
    raw = os.getenv("FERNET_KEY")
    if raw:
        return Fernet(raw.encode())
    key = Fernet.generate_key()
    print(
        f"[WebSession] FERNET_KEY 미설정 — 임시 키 사용 (재시작 시 모든 세션 키 초기화).\n"
        f"[WebSession] 영구 저장을 원하면 환경변수에 추가: FERNET_KEY={key.decode()}"
    )
    return Fernet(key)


_fernet = _init_fernet()

# session_id(str) → WebSession
_store: dict[str, "WebSession"] = {}


@dataclass
class WebSession:
    session_id: str
    repo_url: str
    owner: str
    repo_name: str
    review_text: str                 # 수정 계획 생성 입력용 (구조 + 청크 + 요약 합본)
    file_contents: dict[str, str]    # {상대경로: 파일내용} — CodeFixer 입력용
    api_key_encrypted: bytes         # Fernet 암호화된 Anthropic API 키
    repo_path: Path | None = None    # 로컬 클론 경로 (종료 시 삭제)
    fix_plan: FixPlan | None = None  # 수정 계획 (생성 후 저장, 재사용)


def create(
    repo_url: str,
    owner: str,
    repo_name: str,
    review_text: str,
    file_contents: dict[str, str],
    api_key: str,
    repo_path: Path | None = None,
) -> WebSession:
    """새 세션을 생성하고 저장 후 반환. api_key는 Fernet 암호화해서 저장."""
    session_id = str(uuid.uuid4())
    session = WebSession(
        session_id=session_id,
        repo_url=repo_url,
        owner=owner,
        repo_name=repo_name,
        review_text=review_text,
        file_contents=file_contents,
        api_key_encrypted=_fernet.encrypt(api_key.encode()),
        repo_path=repo_path,
    )
    _store[session_id] = session
    return session


def get(session_id: str) -> WebSession | None:
    """session_id로 세션 조회. 없으면 None."""
    return _store.get(session_id)


def get_api_key(session_id: str) -> str | None:
    """세션의 암호화된 API 키를 복호화해서 반환. 세션 없으면 None."""
    session = _store.get(session_id)
    if not session:
        return None
    return _fernet.decrypt(session.api_key_encrypted).decode()


def save(session: WebSession) -> None:
    """세션 상태 변경 후 명시적으로 저장할 때 사용 (fix_plan 업데이트 등)."""
    _store[session.session_id] = session


def clear(session_id: str) -> None:
    """세션 삭제, API 키 참조 해제, 로컬 클론 정리."""
    session = _store.pop(session_id, None)
    if session and session.repo_path:
        from core.cloner import RepoCloner
        RepoCloner().cleanup(session.repo_path)
