"""
tests/test_reviewer.py — CodeReviewer 통합 테스트 (LLM mock 사용)
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
from agent.reviewer import CodeReviewer, ReviewResult
from agent.gemini_client import LLMClient


@pytest.fixture
def mock_llm():
    """LLM API 호출을 mock으로 대체."""
    llm = MagicMock(spec=LLMClient)
    llm.generate = AsyncMock(return_value="## Mock Review\n테스트 리뷰 결과입니다.")
    return llm


@pytest.fixture
def mock_clone(tmp_path, monkeypatch):
    """실제 git clone 없이 tmp_path를 반환."""
    (tmp_path / "main.py").write_text("def hello(): return 'world'")
    (tmp_path / "README.md").write_text("# Test Repo")

    monkeypatch.setattr(
        "agent.reviewer.RepoCloner.clone",
        lambda self, url: tmp_path,
    )
    monkeypatch.setattr(
        "agent.reviewer.RepoCloner.cleanup",
        lambda self, path: None,
    )
    return tmp_path


@pytest.mark.asyncio
async def test_review_returns_result(mock_llm, mock_clone):
    reviewer = CodeReviewer(llm=mock_llm)
    result = await reviewer.review("https://github.com/test/repo")

    assert isinstance(result, ReviewResult)
    assert result.repo_url == "https://github.com/test/repo"
    assert len(result.final_summary) > 0


@pytest.mark.asyncio
async def test_review_cleanup_called_on_error(monkeypatch):
    """에러 발생 시에도 cleanup이 호출되어야 한다."""
    cleanup_called = []

    monkeypatch.setattr(
        "agent.reviewer.RepoCloner.clone",
        lambda self, url: (_ for _ in ()).throw(ValueError("clone failed")),
    )
    monkeypatch.setattr(
        "agent.reviewer.RepoCloner.cleanup",
        lambda self, path: cleanup_called.append(path),
    )

    llm = MagicMock(spec=LLMClient)
    reviewer = CodeReviewer(llm=llm)
    with pytest.raises(ValueError):
        await reviewer.review("https://github.com/bad/repo")
