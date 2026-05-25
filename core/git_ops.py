"""
core/git_ops.py — 로컬 git 작업 및 GitHub PR 생성
"""

from dataclasses import dataclass
from pathlib import Path

import httpx
from git import Repo


@dataclass
class FilePatch:
    path: str           # 파일 경로 (레포 루트 기준)
    new_content: str    # 수정된 전체 파일 내용


class GitHubOps:
    BASE = "https://api.github.com"

    def __init__(self, token: str):
        self._token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _get_default_branch(self, owner: str, repo: str) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.BASE}/repos/{owner}/{repo}",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()["default_branch"]

    async def create_pr(
        self,
        owner: str,
        repo: str,
        head: str,
        base: str,
        title: str,
        body: str,
    ) -> str:
        """GitHub PR 생성 후 URL 반환."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.BASE}/repos/{owner}/{repo}/pulls",
                headers=self._headers,
                json={"title": title, "body": body, "head": head, "base": base},
            )
            resp.raise_for_status()
            return resp.json()["html_url"]

    def apply_patches_and_push(
        self,
        repo_path: Path,
        owner: str,
        repo: str,
        patches: list[FilePatch],
        branch_name: str,
    ) -> None:
        """로컬 클론에 패치 적용 후 새 브랜치로 push."""
        git_repo = Repo(repo_path)

        # 새 브랜치 생성
        git_repo.git.checkout("-b", branch_name)

        # 파일 수정
        for patch in patches:
            file_path = repo_path / patch.path
            file_path.write_text(patch.new_content, encoding="utf-8")

        # author 정보 설정 (서버 환경에서 global config 없을 때 대비)
        with git_repo.config_writer() as cfg:
            cfg.set_value("user", "email", "prism@render.com")
            cfg.set_value("user", "name", "PRism Bot")

        # 스테이징 + 커밋
        git_repo.git.add("-A")
        git_repo.git.commit("-m", "fix: PRism 자동 코드 리뷰 수정")

        # GITHUB_TOKEN으로 push
        remote_url = f"https://{self._token}@github.com/{owner}/{repo}.git"
        git_repo.git.push(remote_url, branch_name)

    async def apply_and_create_pr(
        self,
        repo_path: Path,
        owner: str,
        repo: str,
        patches: list[FilePatch],
        branch_name: str,
        pr_title: str,
        pr_body: str,
    ) -> str:
        """패치 적용 → push → PR 생성. PR URL 반환."""
        base_branch = await self._get_default_branch(owner, repo)
        self.apply_patches_and_push(repo_path, owner, repo, patches, branch_name)
        return await self.create_pr(
            owner, repo,
            head=branch_name,
            base=base_branch,
            title=pr_title,
            body=pr_body,
        )
