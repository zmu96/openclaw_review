"""
tests/test_cloner.py — RepoCloner 단위 테스트
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.cloner import RepoCloner


def test_extract_repo_name_https():
    cloner = RepoCloner()
    assert cloner._extract_repo_name("https://github.com/user/my-repo") == "my-repo"


def test_extract_repo_name_git_suffix():
    cloner = RepoCloner()
    assert cloner._extract_repo_name("https://github.com/user/my-repo.git") == "my-repo"


def test_extract_repo_name_trailing_slash():
    cloner = RepoCloner()
    assert cloner._extract_repo_name("https://github.com/user/my-repo/") == "my-repo"


@patch("core.cloner.Repo")
def test_clone_calls_git(mock_repo_cls, tmp_path):
    cloner = RepoCloner(base_dir=str(tmp_path))
    cloner.clone("https://github.com/user/test-repo")
    mock_repo_cls.clone_from.assert_called_once()


def test_cleanup_removes_directory(tmp_path):
    target = tmp_path / "some-repo"
    target.mkdir()
    (target / "file.py").write_text("print('hello')")

    cloner = RepoCloner()
    cloner.cleanup(target)
    assert not target.exists()
