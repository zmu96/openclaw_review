"""
core/pr_chunker.py — PR diff 파싱, 압축, 청킹
# inspired by pr-agent/algo/pr_processing.py  (diff 파싱 및 압축 전략)
# inspired by pr-agent/algo/token_handler.py  (토큰 예산 관리)
"""

from dataclasses import dataclass
from pathlib import Path

# 리뷰 의미 없는 파일 확장자 (바이너리, 자동 생성 파일 등)
# inspired by pr-agent/algo/pr_processing.py
SKIP_EXTENSIONS = {
    ".lock", ".min.js", ".min.css",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".pdf", ".zip", ".tar", ".gz",
    ".woff", ".woff2", ".ttf", ".eot",
}

# 청크당 최대 토큰 예산 (Gemini Flash 무료 티어 기준)
# inspired by pr-agent/algo/token_handler.py
MAX_TOKENS_PER_CHUNK = 800_000
CHARS_PER_TOKEN = 4

# 파일 하나의 patch 최대 줄 수 — 초과 시 앞부분만 유지
MAX_PATCH_LINES = 200


@dataclass
class FileDiff:
    filename: str
    status: str       # added | modified | removed | renamed
    additions: int
    deletions: int
    patch: str | None  # None이면 바이너리 또는 패치 없음


class PRDiffChunker:
    """
    GitHub Files API 응답을 받아 Gemini 리뷰용 청크 문자열 목록으로 변환합니다.
    큰 PR도 토큰 초과 없이 처리하기 위해 압축 및 청킹을 수행합니다.
    """

    def parse_files(self, files: list[dict]) -> list[FileDiff]:
        """GitHub API files 응답 → FileDiff 목록. 불필요한 파일은 제외."""
        result = []
        for f in files:
            ext = Path(f["filename"]).suffix.lower()
            if ext in SKIP_EXTENSIONS:
                continue
            if f.get("status") == "unchanged":
                continue
            result.append(FileDiff(
                filename=f["filename"],
                status=f.get("status", "modified"),
                additions=f.get("additions", 0),
                deletions=f.get("deletions", 0),
                patch=f.get("patch"),
            ))
        return result

    def compress(self, file_diffs: list[FileDiff]) -> list[FileDiff]:
        """
        patch가 너무 긴 파일은 앞부분만 유지하고 생략 표시를 붙입니다.
        # inspired by pr-agent/algo/pr_processing.py — PR Compression 전략
        """
        compressed = []
        for fd in file_diffs:
            if fd.patch is None:
                continue
            lines = fd.patch.splitlines()
            if len(lines) > MAX_PATCH_LINES:
                kept = "\n".join(lines[:MAX_PATCH_LINES])
                fd = FileDiff(
                    filename=fd.filename,
                    status=fd.status,
                    additions=fd.additions,
                    deletions=fd.deletions,
                    patch=f"{kept}\n... (이하 {len(lines) - MAX_PATCH_LINES}줄 생략)",
                )
            compressed.append(fd)
        return compressed

    def build_chunks(self, file_diffs: list[FileDiff]) -> list[str]:
        """
        FileDiff 목록을 토큰 예산에 맞게 청크 문자열 목록으로 묶습니다.
        # inspired by pr-agent/algo/token_handler.py
        """
        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0

        for fd in file_diffs:
            block = self._format_file_diff(fd)
            tokens = len(block) // CHARS_PER_TOKEN

            if current_tokens + tokens > MAX_TOKENS_PER_CHUNK and current:
                chunks.append("\n\n".join(current))
                current = []
                current_tokens = 0

            current.append(block)
            current_tokens += tokens

        if current:
            chunks.append("\n\n".join(current))

        return chunks

    def _format_file_diff(self, fd: FileDiff) -> str:
        patch = fd.patch or "(바이너리 파일 또는 패치 없음)"
        return (
            f"### `{fd.filename}` [{fd.status}]  "
            f"+{fd.additions} / -{fd.deletions}\n"
            f"```diff\n{patch}\n```"
        )
