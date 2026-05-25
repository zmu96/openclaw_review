"""
core/cloner.py — GitHub 레포지토리 클론 및 정리
"""

import os
import stat
import sys
import shutil
from pathlib import Path
from git import Repo, GitCommandError


def _remove_readonly(func, path, _):
    """읽기 전용 파일의 속성을 해제하고 재시도합니다 (Windows .git 폴더 대응)."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _rmtree(path: Path) -> None:
    """Python 3.9/3.12 양쪽 호환 rmtree (onexc vs onerror)."""
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_remove_readonly)
    else:
        shutil.rmtree(path, onerror=_remove_readonly)


class RepoCloner:
    def __init__(self, base_dir: str | None = None):
        self.base_dir = base_dir or os.getenv("CLONE_BASE_DIR", "/tmp/prism")
        Path(self.base_dir).mkdir(parents=True, exist_ok=True)

    def clone(self, repo_url: str) -> Path:
        """레포를 클론하고 로컬 경로를 반환합니다."""
        repo_name = self._extract_repo_name(repo_url)
        clone_path = Path(self.base_dir) / repo_name

        if clone_path.exists():
            _rmtree(clone_path)

        try:
            Repo.clone_from(repo_url, clone_path, depth=1)  # shallow clone으로 속도 개선
        except GitCommandError as e:
            raise ValueError(f"레포 클론 실패: {e}") from e

        return clone_path

    def cleanup(self, repo_path: Path) -> None:
        """분석 완료 후 클론된 디렉토리를 삭제합니다."""
        if repo_path.exists():
            _rmtree(repo_path)

    def _extract_repo_name(self, repo_url: str) -> str:
        name = repo_url.rstrip("/").split("/")[-1]
        return name.removesuffix(".git")
