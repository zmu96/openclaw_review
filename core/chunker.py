"""
core/chunker.py — Gemini 무료 티어 토큰 예산 관리 및 파일 청킹

"""

from pathlib import Path
from core.analyzer import FileInfo, ProjectStructure

# 요청당 안전 토큰 상한
MAX_TOKENS_PER_REQUEST = 800_000
# 글자 수 → 토큰 수 근사치 (영어 기준 4자 ≈ 1토큰)
CHARS_PER_TOKEN = 4

# ── 무료 티어 보호 설정 ──────────────────────
MAX_FILES = 30          # 분석할 파일 최대 개수 (중요도 높은 순)
MAX_CHUNKS = 3          # Gemini 청크 요청 최대 횟수 (구조+요약 포함 총 5회)
MAX_FILE_SIZE_KB = 100  # 단일 파일 최대 크기 (초과 시 스킵)


def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


class FileChunker:
    """
    파일 목록을 Gemini 요청당 토큰 한도에 맞게 묶음(chunk)으로 나눕니다.
    우선순위: 설정 파일 > 작은 파일 순. 파일 수와 청크 수를 제한해 무료 티어를 보호합니다.
    """

    def build_chunks(self, structure: ProjectStructure) -> list[list[FileInfo]]:
        # 중요도 순 정렬
        # 1순위: 설정 파일 (프로젝트 구조 파악에 필수)
        # 2순위: 진입점 파일 (main.py, app.py 등)
        # 3순위: import 횟수 많은 파일 (다른 파일이 많이 의존 = 핵심 모듈)
        # 4순위: 파일 크기 작은 순 (토큰 절약)
        prioritized = sorted(
            structure.config_files + structure.code_files,
            key=lambda f: (
                not f.is_config,
                not f.is_entry_point,
                -f.import_count,
                f.size_bytes,
            ),
        )

        # 너무 큰 파일 스킵 + 최대 파일 수 제한
        filtered = [
            f for f in prioritized
            if f.size_bytes <= MAX_FILE_SIZE_KB * 1024
        ][:MAX_FILES]

        chunks: list[list[FileInfo]] = []
        current_chunk: list[FileInfo] = []
        current_tokens = 0

        for file_info in filtered:
            try:
                content = file_info.path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            file_tokens = estimate_tokens(content)

            if current_tokens + file_tokens > MAX_TOKENS_PER_REQUEST:
                if current_chunk:
                    chunks.append(current_chunk)
                    if len(chunks) >= MAX_CHUNKS:
                        return chunks
                current_chunk = [file_info]
                current_tokens = file_tokens
            else:
                current_chunk.append(file_info)
                current_tokens += file_tokens

        if current_chunk:
            chunks.append(current_chunk)

        return chunks[:MAX_CHUNKS]

    def read_chunk_contents(self, chunk: list[FileInfo]) -> str:
        """청크의 파일 내용을 하나의 문자열로 합칩니다."""
        parts = []
        for file_info in chunk:
            try:
                content = file_info.path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                content = "(파일을 읽을 수 없습니다)"
            parts.append(
                f"### 파일: {file_info.relative_path}\n```\n{content}\n```"
            )
        return "\n\n".join(parts)
