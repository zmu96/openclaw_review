"""
agent/gemini_client.py — Anthropic Claude LLM 클라이언트
"""

import os
import re
import anthropic

_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
_MOCK_MODE = os.getenv("MOCK_MODE", "").lower() == "true"

# ── Mock 응답 (MOCK_MODE=true 일 때 사용) ──────────────────────────

_MOCK_STRUCTURE_REVIEW = """\
## 구조 분석 [MOCK]

**아키텍처 패턴:** 레이어드 아키텍처
**주요 기술 스택:** Python, Discord.py, Anthropic API

디렉토리 구조는 전반적으로 잘 분리되어 있습니다.
"""

# FILE: 패턴 없음 → code_fixer._select_files 가 전체 파일 반환
_MOCK_CHUNK_REVIEW = """\
## 코드 리뷰 [MOCK]

전반적으로 양호하지만 일부 개선이 필요합니다.
예외 처리 강화 및 코드 중복 제거를 권장합니다.
"""

_MOCK_FINAL_SUMMARY = """\
## DISCORD_CARD
전체 점수: 7.5/10
코드 품질: ⭐⭐⭐⭐☆
보안:      ⭐⭐⭐☆☆
구조:      ⭐⭐⭐⭐☆
한 줄 요약: 전반적으로 잘 구성되었으나 일부 개선이 필요합니다.
즉시 수정 필요: 2건
개선 권장: 3건
잘 작성된 부분: 4건
핵심 문제: 예외 처리 누락 및 코드 중복
총평: 코드 품질이 양호하며 구조도 잘 설계되어 있습니다.
가장 심각한 문제: 예외 처리 미흡으로 런타임 오류 가능성
보안 이슈: 없음
잘된 점: 모듈화, 명확한 변수명, 일관된 코딩 스타일

## 상세 리뷰

### 주요 발견 사항
1. 예외 처리 강화 필요
2. 코드 중복 일부 존재

### 우선 개선 항목 Top 5
1. 예외 처리 추가
2. 입력 검증 강화
3. 로깅 개선
4. 테스트 코드 추가
5. 문서화 보완

### 잘 작성된 부분
- 명확한 변수명과 함수명
- 일관된 코드 스타일
"""


def _mock_fix_response(prompt: str) -> str:
    """프롬프트의 파일 목록에서 첫 번째 경로를 추출해 가짜 패치 반환."""
    m = re.search(r'  - (.+)', prompt)
    first_file = m.group(1).strip() if m else ""
    file_block = (
        f"FILE_START:{first_file}\n"
        "# [MOCK MODE] Mock 모드에서 생성된 예시 수정 내용입니다.\n"
        "# 실제 API를 사용하면 AI가 분석한 수정 사항이 적용됩니다.\n"
        "FILE_END\n"
    ) if first_file else ""
    return (
        "SUMMARY_START\n"
        "[MOCK] 자동 수정 계획입니다. 실제 API를 사용하지 않습니다.\n"
        "- 예외 처리 개선\n"
        "- 코드 품질 향상\n"
        "SUMMARY_END\n\n"
        + file_block
    )


class LLMClient:
    def __init__(self, api_key: str):
        self._client = None if _MOCK_MODE else anthropic.AsyncAnthropic(api_key=api_key)

    async def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        if _MOCK_MODE:
            if "SUMMARY_START" in prompt:   # code_fixer._FIX_PROMPT
                return _mock_fix_response(prompt)
            elif "DISCORD_CARD" in prompt:  # prompts.build_summary_prompt
                return _MOCK_FINAL_SUMMARY
            elif "청크" in prompt:          # prompts.build_code_review_prompt
                return _MOCK_CHUNK_REVIEW
            else:                           # prompts.build_structure_prompt / 기타
                return _MOCK_STRUCTURE_REVIEW

        async with self._client.messages.stream(
            model=_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            response = await stream.get_final_message()
        return next(b.text for b in response.content if b.type == "text")

    async def validate(self) -> tuple[bool, str]:
        """API 키 유효성 확인. (성공 여부, 오류 메시지) 반환."""
        if _MOCK_MODE:
            return True, ""
        try:
            await self.generate("ping", max_tokens=5)
            return True, ""
        except anthropic.AuthenticationError:
            return False, "유효하지 않은 API 키입니다."
        except anthropic.PermissionDeniedError:
            return False, "API 키에 접근 권한이 없습니다."
        except Exception as e:
            return False, f"검증 중 오류: {e}"
