"""
bot/commands.py — 디스코드 슬래시 커맨드 및 리뷰/수정 플로우
"""

import os
import re
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from agent.reviewer import CodeReviewer
from agent.code_fixer import CodeFixer
from agent.gemini_client import GeminiClient
from core.git_ops import GitHubOps
from core.reporter import Reporter
from bot.review_session import ReviewSession
import bot.review_session as session_store

DISCORD_MAX_CHARS = 1900


def _parse_github_url(url: str) -> tuple[str, str] | None:
    """GitHub URL에서 (owner, repo) 추출. 실패 시 None."""
    m = re.match(r"https?://github\.com/([^/]+)/([^/?\s#]+)", url)
    if not m:
        return None
    return m.group(1), m.group(2).removesuffix(".git")


def _truncate(text: str, limit: int = DISCORD_MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 4] + "\n..."


def _parse_card(text: str) -> dict[str, str]:
    """DISCORD_CARD 섹션에서 key: value 파싱. ## 유무 모두 허용."""
    m = re.search(r'(?:##\s*)?DISCORD_CARD\s*\n([\s\S]*?)(?=\n(?:##\s*)?상세 리뷰|\n##\s|\Z)', text)
    if not m:
        return {}
    card: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            card[key.strip()] = val.strip()
    return card


def _build_discord_message(repo_name: str, final_summary: str) -> str:
    """DISCORD_CARD를 파싱해 단일 Discord 메시지 생성."""
    c = _parse_card(final_summary)
    if not c:
        return f"✅ **리뷰 완료: `{repo_name}`**\n\n{_truncate(final_summary, 1800)}"

    sep = "━━━━━━━━━━━━━━━━━━━━"
    msg = (
        f"📊 **종합 평가: {repo_name}**\n"
        f"{sep}\n"
        f"전체 점수: {c.get('전체 점수', '?')}\n"
        f"코드 품질: {c.get('코드 품질', '?')}\n"
        f"보안:      {c.get('보안', '?')}\n"
        f"구조:      {c.get('구조', '?')}\n"
        f"{sep}\n"
        f"한 줄 요약: {c.get('한 줄 요약', '')}\n"
        f"\n"
        f"🔴 즉시 수정 필요: {c.get('즉시 수정 필요', '?')}\n"
        f"🟡 개선 권장: {c.get('개선 권장', '?')}\n"
        f"🟢 잘 작성된 부분: {c.get('잘 작성된 부분', '?')}\n"
        f"\n"
        f"핵심 문제: {c.get('핵심 문제', '')}\n"
        f"\n"
        f"총평: {c.get('총평', '')}\n"
        f"\n"
        f"▸ 가장 심각한 문제: {c.get('가장 심각한 문제', '')}\n"
        f"▸ 보안 이슈: {c.get('보안 이슈', '')}\n"
        f"▸ 잘된 점: {c.get('잘된 점', '')}"
    )
    return _truncate(msg, 1900)


# ── 버튼 뷰: 리뷰 완료 후 액션 선택 ─────────────────────────────


class ActionView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label="코드 수정 요청", style=discord.ButtonStyle.green, emoji="🔧")
    async def request_fix(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("다른 사용자의 리뷰입니다.", ephemeral=True)
            return

        self.stop()
        await interaction.response.defer(thinking=True)

        session = session_store.get(self.user_id)
        if not session:
            await interaction.followup.send("❌ 세션이 만료되었습니다. `/review`를 다시 실행하세요.")
            return

        await interaction.followup.send("🔧 수정 계획을 생성하고 있습니다. 잠시 기다려 주세요...")

        try:
            llm = GeminiClient()
            fixer = CodeFixer(llm)
            fix_plan = await fixer.generate_fix_plan(session.review_text, session.file_contents)
            session.fix_plan = fix_plan
            session_store.save(self.user_id, session)

            if not fix_plan.patches:
                await interaction.followup.send("✅ 리뷰 결과 수정이 필요한 코드가 없습니다.")
                session_store.clear(self.user_id)
                return

            files_list = "\n".join(f"  • `{f}`" for f in fix_plan.affected_files)
            plan_msg = (
                f"## 📋 수정 계획\n\n"
                f"{_truncate(fix_plan.summary, 800)}\n\n"
                f"**수정 파일 ({len(fix_plan.affected_files)}개):**\n{files_list}\n\n"
                f"이 수정 사항을 GitHub에 PR로 생성할까요?"
            )
            await interaction.followup.send(plan_msg, view=ApprovalView(self.user_id))

        except Exception as e:
            await interaction.followup.send(f"❌ 수정 계획 생성 실패: {e}")
            session_store.clear(self.user_id)

    @discord.ui.button(label="리뷰만 볼게요", style=discord.ButtonStyle.grey, emoji="📄")
    async def review_only(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("다른 사용자의 리뷰입니다.", ephemeral=True)
            return

        self.stop()
        session_store.clear(self.user_id)
        await interaction.response.send_message(
            "리뷰 완료! 코드 수정이 필요하면 `/review`를 다시 실행하세요."
        )


# ── 버튼 뷰: 수정 계획 승인/거절 ────────────────────────────────


class ApprovalView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id

    @discord.ui.button(label="승인 (PR 생성)", style=discord.ButtonStyle.green, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("다른 사용자의 리뷰입니다.", ephemeral=True)
            return

        self.stop()
        await interaction.response.defer(thinking=True)

        session = session_store.get(self.user_id)
        if not session or not session.fix_plan:
            await interaction.followup.send("❌ 세션이 만료되었습니다.")
            return

        await interaction.followup.send("🚀 GitHub에 브랜치를 생성하고 PR을 올리는 중...")

        try:
            github_token = os.getenv("GITHUB_TOKEN")
            if not github_token:
                raise ValueError("GITHUB_TOKEN이 설정되지 않았습니다.")
            if not session.repo_path or not session.repo_path.exists():
                raise ValueError("로컬 클론이 존재하지 않습니다. /review를 다시 실행하세요.")

            git_ops = GitHubOps(github_token)
            branch_name = f"PRism/{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            pr_body = (
                "## 🤖 PRism 자동 코드 리뷰 수정\n\n"
                f"### 수정 내용\n{session.fix_plan.summary}\n\n"
                "### 수정 파일\n"
                + "\n".join(f"- `{f}`" for f in session.fix_plan.affected_files)
                + "\n\n*이 PR은 PRism AI 코드 리뷰어가 자동 생성했습니다.*"
            )

            pr_url = await git_ops.apply_and_create_pr(
                repo_path=session.repo_path,
                owner=session.owner,
                repo=session.repo_name,
                patches=session.fix_plan.patches,
                branch_name=branch_name,
                pr_title=f"[PRism] 자동 코드 리뷰 수정 ({datetime.now().strftime('%Y-%m-%d')})",
                pr_body=pr_body,
            )

            await interaction.followup.send(
                f"✅ **PR 생성 완료!**\n{pr_url}\n\n"
                "GitHub에서 확인 후 머지 여부를 결정하세요."
            )

        except Exception as e:
            await interaction.followup.send(f"❌ PR 생성 실패: {e}")

        finally:
            session_store.clear(self.user_id)

    @discord.ui.button(label="거절", style=discord.ButtonStyle.red, emoji="❌")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("다른 사용자의 리뷰입니다.", ephemeral=True)
            return

        self.stop()
        session_store.clear(self.user_id)
        await interaction.response.send_message(
            "취소되었습니다. 수정이 필요하면 `/review`를 다시 실행하세요."
        )


# ── Cog: 슬래시 커맨드 등록 ──────────────────────────────────────


class ReviewCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reviewer = CodeReviewer()
        self.reporter = Reporter()

    @commands.command(name="review")
    async def review_prefix(self, ctx: commands.Context, repo_url: str):
        await self._run_review(ctx.send, repo_url, ctx.author.id)

    @app_commands.command(name="review", description="GitHub 레포지토리를 AI로 코드 리뷰합니다")
    @app_commands.describe(url="리뷰할 GitHub 레포지토리 또는 PR URL")
    async def review_slash(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer(thinking=True)

        async def send(msg: str, **kwargs):
            return await interaction.followup.send(msg, **kwargs)

        await self._run_review(send, url, interaction.user.id)

    async def _run_review(self, send_fn, repo_url: str, user_id: int):
        parsed = _parse_github_url(repo_url)
        if not parsed:
            await send_fn(
                "❌ 올바른 GitHub URL을 입력해 주세요.\n예: `https://github.com/user/repo`"
            )
            return

        owner, repo_name = parsed
        await send_fn(f"🔍 `{repo_url}` 분석을 시작합니다. 잠시 기다려 주세요...")

        try:
            result = await self.reviewer.review(repo_url)

            # 상세 리뷰 전문 합본 (구조 + 청크별 + 최종 요약)
            full_review = "\n\n---\n\n".join(
                [result.structure_review] + result.chunk_reviews + [result.final_summary]
            )
            session_store.save(
                user_id,
                ReviewSession(
                    repo_url=repo_url,
                    owner=owner,
                    repo_name=repo_name,
                    review_text=full_review,
                    file_contents=result.file_contents,
                    repo_path=result.repo_path,
                ),
            )

            # Discord 카드 메시지 생성
            card_msg = _build_discord_message(result.repo_name, result.final_summary)

            # 전체 리뷰 .md 파일 저장
            md_path = self.reporter.save_markdown(result)
            md_file = discord.File(str(md_path), filename=md_path.name)

            await send_fn(card_msg, file=md_file, view=ActionView(user_id))

        except Exception as e:
            await send_fn(f"❌ 오류 발생: {e}")
