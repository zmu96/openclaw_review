"""
core/reporter.py — 리뷰 결과를 Markdown / HTML로 변환하여 파일로 저장
"""

import os
from pathlib import Path
from datetime import datetime
from agent.reviewer import ReviewResult

OUTPUT_DIR = Path(os.getenv("REPORT_OUTPUT_DIR", "./reports/output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class Reporter:
    # ── Markdown (디스코드 봇용) ──────────────────────

    def to_markdown(self, result: ReviewResult) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        file_list = "\n".join(
            f"  {p}" for p in sorted(result.file_contents.keys())
        )
        sections = [
            f"# 코드 리뷰 보고서: `{result.repo_name}`",
            f"> 분석 시각: {now}  \n> 레포지토리: {result.repo_url}",
            "---",
            "## 📁 파일 구조 분석",
            f"```\n{file_list}\n```",
            result.structure_review,
            "---",
            "## 🔍 코드 리뷰",
        ]
        for i, review in enumerate(result.chunk_reviews, start=1):
            sections.append(f"### 파트 {i}/{len(result.chunk_reviews)}")
            sections.append(review)
        sections += [
            "---",
            "## 📋 종합 요약",
            result.final_summary,
        ]
        return "\n\n".join(sections)

    def save_markdown(self, result: ReviewResult) -> Path:
        content = self.to_markdown(result)
        filename = f"{result.repo_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        path = OUTPUT_DIR / filename
        path.write_text(content, encoding="utf-8")
        return path

    # ── HTML (웹 UI용) ────────────────────────────────

    def to_html(self, result: ReviewResult) -> str:
        import html as html_module

        def md_block(text: str) -> str:
            return f'<pre class="review-text">{html_module.escape(text)}</pre>'

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        chunk_sections = ""
        for i, review in enumerate(result.chunk_reviews, start=1):
            chunk_sections += f"""
            <section class="review-section">
                <h3>파트 {i} / {len(result.chunk_reviews)}</h3>
                {md_block(review or "")}
            </section>"""

        dir_summary_html = "".join(
            f'<div class="dir-entry">'
            f'<code class="dir-path">{html_module.escape(e.display_path)}</code>'
            f'<span class="dir-desc">{html_module.escape(e.description)}</span>'
            f'<span class="dir-count">{e.file_count}개 파일</span>'
            f'</div>'
            for e in result.dir_summaries
        )

        return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>코드 리뷰: {html_module.escape(result.repo_name)}</title>
  <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
  <header>
    <h1>코드 리뷰 보고서</h1>
    <p class="meta">
      <strong>{html_module.escape(result.repo_name)}</strong> &middot; {now}
      &middot; <a href="{html_module.escape(result.repo_url)}" target="_blank">레포지토리</a>
    </p>
  </header>
  <main>
    <section class="review-section">
      <h2>📁 파일 구조</h2>
      <div class="dir-summary">{dir_summary_html}</div>
      {md_block(result.structure_review or "")}
    </section>
    <section class="review-section">
      <h2>🔍 코드 리뷰</h2>
      {chunk_sections}
    </section>
    <section class="review-section summary">
      <h2>📋 종합 요약</h2>
      {md_block(result.final_summary)}
    </section>
  </main>
</body>
</html>"""

    def save_html(self, result: ReviewResult) -> Path:
        content = self.to_html(result)
        filename = f"{result.repo_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        path = OUTPUT_DIR / filename
        path.write_text(content, encoding="utf-8")
        return path
