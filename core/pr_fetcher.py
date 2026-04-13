"""
core/pr_fetcher.py — GitHub API 호출: PR 메타데이터 및 변경 파일 조회
# inspired by pr-agent/git_providers/github_provider.py
"""

import re
import httpx

GITHUB_API_BASE = "https://api.github.com"


class PRFetchError(Exception):
    pass


class PRFetcher:
    def __init__(self, token: str):
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def parse_pr_url(self, url: str) -> tuple[str, str, int]:
        """GitHub PR URL에서 owner, repo, pr_number 추출."""
        match = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", url)
        if not match:
            raise PRFetchError(f"올바르지 않은 PR URL 형식입니다: {url}")
        owner, repo, number = match.groups()
        return owner, repo, int(number)

    async def fetch_pr_info(self, owner: str, repo: str, pr_number: int) -> dict:
        """PR 제목, 설명, 브랜치 등 메타데이터 조회."""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}"
        async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
            resp = await client.get(url)
            _raise_for_status(resp)
            return resp.json()

    async def fetch_files(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        """PR에서 변경된 파일 목록 및 각 파일의 patch 조회."""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/files"
        async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
            resp = await client.get(url, params={"per_page": 100})
            _raise_for_status(resp)
            return resp.json()


def _raise_for_status(resp: httpx.Response) -> None:
    """GitHub API 에러를 사람이 읽기 쉬운 메시지로 변환.
    # inspired by pr-agent/git_providers/github_provider.py
    """
    if resp.status_code == 401:
        raise PRFetchError("GitHub 인증 실패: GITHUB_TOKEN을 확인하세요.")
    if resp.status_code == 403:
        raise PRFetchError("GitHub API 접근 거부: 권한 또는 rate limit을 확인하세요.")
    if resp.status_code == 404:
        raise PRFetchError("PR을 찾을 수 없습니다. URL 또는 레포 공개 여부를 확인하세요.")
    resp.raise_for_status()
