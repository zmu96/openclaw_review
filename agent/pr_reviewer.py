"""
agent/pr_reviewer.py — PR 리뷰 파이프라인 오케스트레이터
"""

import asyncio
import os
from dataclasses import dataclass

from core.pr_fetcher import PRFetcher
from core.pr_chunker import PRDiffChunker
from core.pr_commenter import PRCommenter
from agent.gemini_client import LLMClient
from agent.pr_prompts import build_pr_review_prompt, build_pr_final_prompt


@dataclass
class PRReviewResult:
    pr_url: str
    pr_title: str
    pr_number: int
    owner: str
    repo: str
    final_review: str
    comment_url: str


class PRReviewer:
    def __init__(self, llm: LLMClient):
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            raise ValueError("GITHUB_TOKEN 환경변수가 설정되지 않았습니다.")
        self.fetcher = PRFetcher(token)
        self.chunker = PRDiffChunker()
        self.commenter = PRCommenter(token)
        self.llm = llm

    async def review(self, pr_url: str) -> PRReviewResult:
        # 1. URL 파싱
        owner, repo, pr_number = self.fetcher.parse_pr_url(pr_url)

        # 2. PR 메타데이터 + 변경 파일을 병렬 조회
        pr_info, files = await asyncio.gather(
            self.fetcher.fetch_pr_info(owner, repo, pr_number),
            self.fetcher.fetch_files(owner, repo, pr_number),
        )

        # 3. diff 파싱 → 압축 → 청킹
        file_diffs = self.chunker.parse_files(files)
        compressed = self.chunker.compress(file_diffs)
        chunks = self.chunker.build_chunks(compressed)

        if not chunks:
            raise ValueError("리뷰할 코드 변경이 없습니다 (바이너리/잠금 파일만 변경된 PR).")

        # 4. 청크별 부분 리뷰 생성
        partial_reviews = []
        for i, chunk in enumerate(chunks, start=1):
            prompt = build_pr_review_prompt(pr_info, chunk, i, len(chunks))
            partial_reviews.append(await self.llm.generate(prompt))

        # 5. 종합 최종 리뷰 생성
        final_prompt = build_pr_final_prompt(pr_info, partial_reviews)
        final_review = await self.llm.generate(final_prompt)

        # 6. GitHub PR에 코멘트 게시
        comment_url = await self.commenter.post_review_comment(
            owner, repo, pr_number, final_review
        )

        return PRReviewResult(
            pr_url=pr_url,
            pr_title=pr_info.get("title", ""),
            pr_number=pr_number,
            owner=owner,
            repo=repo,
            final_review=final_review,
            comment_url=comment_url,
        )
