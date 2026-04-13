"""
agent/pr_prompts.py — PR 리뷰용 Gemini 프롬프트 템플릿
# inspired by pr-agent/tools/pr_reviewer.py (리뷰 항목 구성 방식)
"""

SYSTEM_CONTEXT = """
당신은 시니어 소프트웨어 엔지니어입니다.
GitHub Pull Request의 코드 변경(diff)을 분석하여 구체적이고 실용적인 코드 리뷰를 작성합니다.
추상적인 조언 대신 특정 파일명과 코드 내용을 직접 언급하세요.
""".strip()


def build_pr_review_prompt(
    pr_info: dict, diff_chunk: str, chunk_idx: int, total_chunks: int
) -> str:
    """청크 단위 부분 리뷰 프롬프트."""
    title = pr_info.get("title", "")
    body = (pr_info.get("body") or "설명 없음")[:500]
    base_branch = pr_info.get("base", {}).get("ref", "main")
    head_branch = pr_info.get("head", {}).get("ref", "")

    return f"""{SYSTEM_CONTEXT}

## PR 정보
- 제목: {title}
- 브랜치: `{head_branch}` → `{base_branch}`
- 설명: {body}

## 변경된 코드 (파트 {chunk_idx}/{total_chunks})
{diff_chunk}

---

위 diff를 아래 항목별로 리뷰해 주세요:

### 1. 버그 / 잠재적 오류
(로직 오류, 예외 처리 누락, 경계값 문제. 없으면 "없음")

### 2. 보안 이슈
(입력 검증 부재, 민감 정보 노출, 인젝션 위험. 없으면 "없음")

### 3. 코드 품질
(가독성, 네이밍, 중복, 복잡도)

### 4. 개선 제안
(파일명과 내용을 직접 언급하며 우선순위 높은 순으로)

Markdown으로 작성하세요.
"""


def build_pr_final_prompt(pr_info: dict, partial_reviews: list[str]) -> str:
    """부분 리뷰들을 종합하여 GitHub PR에 올릴 최종 코멘트를 생성합니다.
    # inspired by pr-agent/tools/pr_reviewer.py (종합 리뷰 구성 방식)
    """
    combined = "\n\n---\n\n".join(partial_reviews)
    title = pr_info.get("title", "")

    return f"""{SYSTEM_CONTEXT}

아래는 PR "{title}"의 각 파트별 코드 리뷰 결과입니다.

{combined}

---

위 내용을 종합하여 GitHub PR 코멘트 형식으로 작성해 주세요.
이모지와 Markdown을 활용하세요.

형식:

## 📋 리뷰 요약
(전체 변경의 한 문단 요약)

## 🔴 반드시 수정 (Blocking)
(머지 전 필수 수정 항목. 없으면 "없음")

## 🟡 권고 사항 (Non-blocking)
(개선 권장 항목)

## 🟢 잘 작성된 부분
(칭찬할 만한 코드나 구조)

## 📊 변경 영향도
- 위험도: 높음 / 중간 / 낮음
- 테스트 필요 여부: Yes / No

---
*🤖 이 리뷰는 AI(Gemini)가 자동 생성했습니다.*
"""
