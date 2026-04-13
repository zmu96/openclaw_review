"""
agent/prompts.py — Gemini 프롬프트 템플릿 모음
"""

SYSTEM_CONTEXT = """
당신은 시니어 소프트웨어 엔지니어입니다.
주어진 코드를 분석하여 구체적이고 실용적인 코드 리뷰를 작성합니다.
추상적인 조언보다 코드의 특정 라인이나 패턴을 직접 언급하며 개선 방안을 제시합니다.
""".strip()


def build_structure_prompt(file_paths: list[str], language_stats: dict) -> str:
    paths_text = "\n".join(f"  {p}" for p in file_paths)
    stats_text = "\n".join(
        f"  - {ext}: {count}개" for ext, count in sorted(language_stats.items())
    )
    return f"""{SYSTEM_CONTEXT}

아래는 프로젝트의 전체 파일 목록과 언어 통계입니다.

## 파일 목록
{paths_text}

## 언어별 파일 수
{stats_text}

위 정보를 바탕으로 다음을 분석해 주세요:
1. 프로젝트의 전체적인 아키텍처 패턴 (MVC, 레이어드, 마이크로서비스 등)
2. 디렉토리/파일 구조의 적절성과 개선 제안
3. 주요 기술 스택

JSON 형식 없이 Markdown으로 작성해 주세요.
"""


def build_code_review_prompt(chunk_content: str, chunk_index: int, total_chunks: int) -> str:
    return f"""{SYSTEM_CONTEXT}

아래는 프로젝트 코드의 일부입니다 (청크 {chunk_index}/{total_chunks}).

{chunk_content}

다음 항목을 리뷰해 주세요:

### 1. 코드 품질
- 가독성, 네이밍 컨벤션, 중복 코드 여부

### 2. 잠재적 버그 / 보안 이슈
- 예외 처리 미흡, 입력 검증 부재, 보안 취약점

### 3. 구조 및 설계
- 단일 책임 원칙, 결합도/응집도, 의존성 방향

### 4. 개선 제안
- 우선순위 높은 순으로 구체적인 수정 방안 제시

파일에서 문제를 발견했을 때는 반드시 아래 형식으로 파일명을 명시하세요:
FILE:파일명.kt — 문제 요약
이 형식 없이 언급된 파일은 수정 대상에서 제외됩니다.
"""


def build_summary_prompt(partial_reviews: list[str]) -> str:
    combined = "\n\n---\n\n".join(partial_reviews)
    return f"""{SYSTEM_CONTEXT}

아래는 프로젝트 각 부분에 대한 개별 코드 리뷰 결과입니다.

{combined}

위 내용을 종합하여 아래 두 섹션을 작성해 주세요.

---

## DISCORD_CARD
(아래 형식을 한 글자도 변경하지 말고 값만 채워서 작성)

전체 점수: X.X/10
코드 품질: ⭐⭐⭐☆☆
보안:      ⭐⭐☆☆☆
구조:      ⭐⭐⭐☆☆
한 줄 요약: (한 문장)
즉시 수정 필요: N건
개선 권장: N건
잘 작성된 부분: N건
핵심 문제: (파일명 포함 한 문장)
총평: (한 문장)
가장 심각한 문제: (한 문장)
보안 이슈: (한 문장, 없으면 "없음")
잘된 점: (한 문장)

## 상세 리뷰
(주요 발견 사항, 우선 개선 항목 Top 5, 잘 작성된 부분을 Markdown으로 상세히 작성)
"""
