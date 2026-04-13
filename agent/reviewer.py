"""
agent/reviewer.py — 리뷰 오케스트레이터 (전체 파이프라인 조율)
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from core.cloner import RepoCloner
from core.analyzer import ProjectAnalyzer, ProjectStructure, DirSummary
from core.chunker import FileChunker
from agent.gemini_client import GeminiClient
from agent.prompts import (
    build_structure_prompt,
    build_code_review_prompt,
    build_summary_prompt,
)

# Gemini 무료 티어: 분당 15 요청 → 요청 사이 최소 대기
REQUEST_INTERVAL_SECONDS = 5


@dataclass
class ReviewResult:
    repo_url: str
    repo_name: str
    structure_review: str
    chunk_reviews: list[str]
    final_summary: str
    dir_summaries: list[DirSummary]
    language_stats: dict
    file_contents: dict[str, str] = field(default_factory=dict)  # 패치 생성용
    repo_path: Path | None = None  # 로컬 클론 경로 (호출자가 cleanup 책임)


class CodeReviewer:
    def __init__(self):
        self.cloner = RepoCloner()
        self.analyzer = ProjectAnalyzer()
        self.chunker = FileChunker()
        self.gemini = GeminiClient()

    async def review(self, repo_url: str) -> ReviewResult:
        repo_path = None
        try:
            # 1. 클론
            repo_path = self.cloner.clone(repo_url)

            # 2. 구조 분석
            structure: ProjectStructure = self.analyzer.analyze(repo_path)

            # 3. 구조 리뷰 — 전체 파일 경로 목록을 그대로 전달
            all_file_paths = [
                f.relative_path.replace("\\", "/")
                for f in structure.all_files
            ]
            structure_prompt = build_structure_prompt(
                all_file_paths, structure.language_stats
            )
            structure_review = await self.gemini.generate(structure_prompt)
            await asyncio.sleep(REQUEST_INTERVAL_SECONDS)

            # 4. 코드 청킹 및 청크별 리뷰
            chunks = self.chunker.build_chunks(structure)
            chunk_reviews = []
            for i, chunk in enumerate(chunks, start=1):
                content = self.chunker.read_chunk_contents(chunk)
                prompt = build_code_review_prompt(content, i, len(chunks))
                review_text = await self.gemini.generate(prompt)
                chunk_reviews.append(review_text)
                if i < len(chunks):
                    await asyncio.sleep(REQUEST_INTERVAL_SECONDS)

            # 5. 최종 요약
            final_prompt = build_summary_prompt([structure_review] + chunk_reviews)
            final_summary = await self.gemini.generate(final_prompt)

            # 6. 파일 내용 캡처 (Discord 코드 수정 플로우용 — cleanup 전에 읽어야 함)
            file_contents: dict[str, str] = {}
            for file_info in structure.code_files:
                try:
                    rel = file_info.relative_path.replace("\\", "/")
                    file_contents[rel] = file_info.path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    pass

            result = ReviewResult(
                repo_url=repo_url,
                repo_name=structure.repo_name,
                structure_review=structure_review,
                chunk_reviews=chunk_reviews,
                final_summary=final_summary,
                dir_summaries=structure.dir_summaries,
                language_stats=structure.language_stats,
                file_contents=file_contents,
                repo_path=repo_path,
            )
            repo_path = None  # 성공 시 finally에서 cleanup 방지
            return result

        finally:
            # 실패 시에만 cleanup (성공 시 repo_path=None으로 스킵)
            if repo_path:
                self.cloner.cleanup(repo_path)
