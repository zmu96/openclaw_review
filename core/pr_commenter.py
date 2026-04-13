"""
core/pr_commenter.py — GitHub PR에 리뷰 코멘트 게시
# inspired by pr-agent/git_providers/github_provider.py
"""

import httpx
from core.pr_fetcher import _raise_for_status

GITHUB_API_BASE = "https://api.github.com"


class PRCommenter:
    def __init__(self, token: str):
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def post_review_comment(
        self, owner: str, repo: str, pr_number: int, body: str
    ) -> str:
        """PR 스레드에 코멘트를 게시하고 게시된 코멘트 URL을 반환합니다."""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
            resp = await client.post(url, json={"body": body})
            _raise_for_status(resp)
            return resp.json()["html_url"]
