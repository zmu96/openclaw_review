"""
agent/code_fixer.py — 리뷰 결과를 바탕으로 실제 코드 패치를 생성합니다.
"""

import re
from dataclasses import dataclass, field

from agent.gemini_client import GeminiClient
from core.git_ops import FilePatch


@dataclass
class FixPlan:
    summary: str                          # 사용자에게 보여줄 수정 계획 요약
    patches: list[FilePatch]              # 실제 파일 패치 목록
    affected_files: list[str] = field(default_factory=list)


_FIX_PROMPT = """\
당신은 코드 리뷰 결과를 바탕으로 실제 코드를 수정하는 AI입니다.

## 코드 리뷰 결과
{review}

## 수정 가능한 파일 목록 (이 목록에 있는 파일만 수정 가능)
{file_list}

## 현재 파일 내용
{files}

## 출력 형식 (반드시 준수)

SUMMARY_START
수정 내용 요약 (한국어, 3-5줄)
SUMMARY_END

FILE_START:파일/경로.py
(수정된 파일의 전체 내용을 여기에 그대로 출력)
FILE_END

## 중요 규칙
1. SUMMARY_START/END와 FILE_START/END 구분자는 반드시 단독 줄에 위치
2. FILE_START 뒤에 콜론(:)과 파일 경로를 붙여서 작성 (예: FILE_START:app/src/main/java/Foo.kt)
3. FILE_START ~ FILE_END 사이에 파일 전체 내용 포함 (절대 부분 수정 금지)
4. 반드시 위 "수정 가능한 파일 목록"에 있는 파일만 수정할 것 — 새 파일 생성 절대 금지
5. SUMMARY에서 수정하겠다고 언급한 파일은 반드시 FILE 블록으로 출력해야 함
6. FILE 블록 없이 언급만 한 파일은 수정된 것으로 간주하지 않음
7. 주석이나 설명 없이 위 형식만 출력
8. TODO 주석, 플레이스홀더, 주석으로만 된 변경은 수정으로 간주하지 않음 — 반드시 실제 코드가 변경되어야 함
9. 보안 이슈(평문 HTTP, 하드코딩된 IP/키 등)는 코드 레벨에서 직접 수정할 것 (예: http → https 변경, 상수 분리 등)
"""

_MISSING_FILES_PROMPT = """\
코드 리뷰 결과를 바탕으로 아래 파일들을 수정해야 합니다.
이전 수정 계획에서 언급했으나 FILE 블록이 누락되었습니다.

## 수정이 필요한 이유 (리뷰 요약)
{summary}

## 누락된 파일 목록 (FILE_START 뒤에 아래 경로를 정확히 그대로 사용할 것)
{missing_file_paths}

## 누락된 파일과 현재 내용
{missing_files_with_content}

위 파일들의 FILE 블록만 아래 형식으로 출력해주세요. 다른 내용은 출력하지 마세요.
경로는 위 "누락된 파일 목록"에 있는 것을 한 글자도 바꾸지 말고 그대로 사용하세요.

FILE_START:파일/경로.kt
(수정된 파일의 전체 내용)
FILE_END
"""

BATCH_TOKEN_LIMIT = 6000   # 배치당 최대 추정 토큰
TOKENS_PER_LINE = 10       # 1줄 ≈ 10토큰


class CodeFixer:
    def __init__(self, llm: GeminiClient):
        self.llm = llm

    async def generate_fix_plan(
        self,
        review_text: str,
        file_contents: dict[str, str],
    ) -> FixPlan:
        """리뷰 결과와 파일 내용을 받아 수정 계획을 생성합니다."""
        selected = self._select_files(review_text, file_contents)
        print(f"[CodeFixer] 선택된 파일 ({len(selected)}개): {list(selected.keys())}")

        batches = self._make_batches(selected)
        print(f"[CodeFixer] 배치 수: {len(batches)} (한도: {BATCH_TOKEN_LIMIT}토큰/배치)")

        all_patches: list[FilePatch] = []
        summary = "(요약 없음)"

        for i, batch in enumerate(batches):
            file_list = "\n".join(f"  - {path}" for path in batch)
            files_str = "\n\n".join(
                f"### {path}\n```\n{content}\n```"
                for path, content in batch.items()
            )
            prompt = _FIX_PROMPT.format(
                review=review_text,
                file_list=file_list,
                files=files_str,
            )
            valid_paths = set(batch.keys())
            response = await self.llm.generate(prompt, temperature=0.0, max_tokens=8192)
            plan = self._parse_response(response, valid_paths)

            if i == 0:
                summary = plan.summary

            # 배치 내 누락 파일 재요청
            missing = self._find_missing_files(plan.summary, plan.patches, valid_paths)
            if missing:
                print(f"[CodeFixer] 배치 {i+1} 누락 FILE 블록 재요청: {missing}")
                missing_files_with_content = "\n\n".join(
                    f"### {path}\n```\n{batch[path]}\n```"
                    for path in missing
                    if path in batch
                )
                missing_file_paths = "\n".join(f"  - {path}" for path in missing)
                follow_up = _MISSING_FILES_PROMPT.format(
                    summary=plan.summary,
                    missing_file_paths=missing_file_paths,
                    missing_files_with_content=missing_files_with_content,
                )
                follow_response = await self.llm.generate(follow_up, temperature=0.0, max_tokens=8192)
                extra = self._parse_response(follow_response, valid_paths)
                existing = {p.path for p in plan.patches}
                for patch in extra.patches:
                    if patch.path not in existing:
                        plan.patches.append(patch)

            existing_paths = {p.path for p in all_patches}
            for patch in plan.patches:
                if patch.path not in existing_paths:
                    all_patches.append(patch)

        return FixPlan(
            summary=summary,
            patches=all_patches,
            affected_files=[p.path for p in all_patches],
        )

    def _select_files(
        self, review_text: str, file_contents: dict[str, str]
    ) -> dict[str, str]:
        """FILE:파일명 패턴으로 실제 이슈가 지적된 파일만 선택."""
        issue_filenames = set(re.findall(r'FILE:(\S+)', review_text))

        # 패턴 미검출 시 (구형 리뷰 형식) 전체 파일 반환
        if not issue_filenames:
            return dict(file_contents)

        result = {}
        for path, content in file_contents.items():
            filename = path.split("/")[-1]
            if filename in issue_filenames:
                result[path] = content
        return result

    def _make_batches(self, file_contents: dict[str, str]) -> list[dict[str, str]]:
        """줄 수 기준 토큰 추정 후 BATCH_TOKEN_LIMIT 단위로 배치 분할."""
        batches: list[dict[str, str]] = []
        current: dict[str, str] = {}
        current_tokens = 0
        for path, content in file_contents.items():
            estimated = len(content.splitlines()) * TOKENS_PER_LINE
            if current and current_tokens + estimated > BATCH_TOKEN_LIMIT:
                batches.append(current)
                current = {}
                current_tokens = 0
            current[path] = content
            current_tokens += estimated
        if current:
            batches.append(current)
        return batches

    def _find_missing_files(
        self, summary: str, patches: list[FilePatch], valid_paths: set[str]
    ) -> list[str]:
        """요약에서 언급됐지만 FILE 블록이 없는 파일 목록 반환."""
        patched = {p.path.split("/")[-1] for p in patches}
        missing = []
        for path in valid_paths:
            filename = path.split("/")[-1]
            stem = filename.rsplit(".", 1)[0]
            if (filename in summary or stem in summary) and filename not in patched:
                missing.append(path)
        return missing

    def _parse_response(self, response: str, valid_paths: set[str]) -> FixPlan:
        # 요약 추출
        summary_match = re.search(r'SUMMARY_START\s*([\s\S]*?)\s*SUMMARY_END', response)
        summary = summary_match.group(1).strip() if summary_match else "(요약 없음)"

        # 파일 패치 추출
        patches = []
        skipped = []
        for m in re.finditer(r'FILE_START:(.+?)\n([\s\S]*?)FILE_END', response):
            path = m.group(1).strip()
            content = m.group(2).rstrip("\n")
            if path in valid_paths:
                patches.append(FilePatch(path=path, new_content=content))
            else:
                skipped.append(path)

        if skipped:
            print(f"[CodeFixer] 존재하지 않는 파일 제외: {skipped}")
        print(f"[CodeFixer] 최종 패치 파일: {[p.path for p in patches]}")

        return FixPlan(
            summary=summary,
            patches=patches,
            affected_files=[p.path for p in patches],
        )
