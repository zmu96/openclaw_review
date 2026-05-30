"""
bot/commands.py — 디스코드 슬래시 커맨드 및 리뷰/수정 플로우
"""

import re
from datetime import datetime

import discord
import httpx
from discord import app_commands
from discord.ext import commands

from agent.reviewer import CodeReviewer
from agent.code_fixer import CodeFixer
from agent.gemini_client import LLMClient
from core.git_ops import GitHubOps
from core.reporter import Reporter
from bot.review_session import ReviewSession
from bot import key_store
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
    def __init__(self, user_id: int, bot: commands.Bot):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.bot = bot

    async def _disable_buttons(self, interaction: discord.Interaction) -> None:
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="코드 수정 요청", style=discord.ButtonStyle.green, emoji="🔧")
    async def request_fix(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("다른 사용자의 리뷰입니다.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        self.stop()
        await self._disable_buttons(interaction)

        session = session_store.get(self.user_id)
        if not session:
            await interaction.followup.send("❌ 세션이 만료되었습니다. `/review`를 다시 실행하세요.")
            return

        # 재계획으로 이미 fix_plan이 있으면 LLM 재호출 없이 바로 ApprovalView 표시
        if session.fix_plan:
            fix_plan = session.fix_plan
        else:
            await interaction.followup.send("🔧 수정 계획을 생성하고 있습니다. 잠시 기다려 주세요...")
            try:
                api_key = key_store.get_key(self.user_id)
                if not api_key:
                    await interaction.followup.send("❌ API 키 세션이 만료되었습니다. `/setup`을 다시 실행하세요.")
                    return
                llm = LLMClient(api_key=api_key)
                fixer = CodeFixer(llm)
                fix_plan = await fixer.generate_fix_plan(session.review_text, session.file_contents)
                session.fix_plan = fix_plan
                session_store.save(self.user_id, session)
            except Exception as e:
                await interaction.followup.send(f"❌ 수정 계획 생성 실패: {e}")
                session_store.clear(self.user_id)
                return

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

    @discord.ui.button(label="다시 계획해줘", style=discord.ButtonStyle.blurple, emoji="🔄")
    async def replan(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("다른 사용자의 리뷰입니다.", ephemeral=True)
            return

        self.stop()
        await interaction.response.send_message("어떻게 수정할까요? 피드백을 입력해주세요.")
        await self._disable_buttons(interaction)

        def check(m: discord.Message) -> bool:
            return m.author.id == self.user_id and m.channel.id == interaction.channel.id

        try:
            feedback_msg = await self.bot.wait_for("message", check=check, timeout=300)
        except TimeoutError:
            await interaction.channel.send("⏰ 피드백 입력 시간이 초과되었습니다. `/review`를 다시 실행하세요.")
            return

        feedback = feedback_msg.content.strip()
        session = session_store.get(self.user_id)
        if not session:
            await interaction.channel.send("❌ 세션이 만료되었습니다. `/review`를 다시 실행하세요.")
            return

        await interaction.channel.send("🔄 피드백을 반영해서 재계획 중입니다. 잠시 기다려 주세요...")

        try:
            api_key = key_store.get_key(self.user_id)
            if not api_key:
                await interaction.channel.send("❌ API 키 세션이 만료되었습니다. `/setup`을 다시 실행하세요.")
                return

            llm = LLMClient(api_key=api_key)
            fixer = CodeFixer(llm)
            fix_plan = await fixer.generate_fix_plan(
                session.review_text, session.file_contents, user_feedback=feedback
            )
            session.fix_plan = fix_plan
            session_store.save(self.user_id, session)

            if not fix_plan.patches:
                await interaction.channel.send("✅ 피드백 반영 결과 수정이 필요한 코드가 없습니다.")
                session_store.clear(self.user_id)
                return

            files_list = "\n".join(f"  • `{f}`" for f in fix_plan.affected_files)
            plan_msg = (
                f"## 📋 재계획 결과 (피드백 반영)\n\n"
                f"**피드백:** {_truncate(feedback, 200)}\n\n"
                f"{_truncate(fix_plan.summary, 700)}\n\n"
                f"**수정 파일 ({len(fix_plan.affected_files)}개):**\n{files_list}\n\n"
                f"다음 작업을 선택해주세요."
            )
            await interaction.channel.send(plan_msg, view=ActionView(self.user_id, self.bot))

        except Exception as e:
            await interaction.channel.send(f"❌ 재계획 실패: {e}")
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
        await self._disable_buttons(interaction)


# ── 버튼 뷰: 수정 계획 승인/거절 ────────────────────────────────


class ApprovalView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    async def _disable_buttons(self, interaction: discord.Interaction) -> None:
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="승인 (PR 생성)", style=discord.ButtonStyle.green, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("다른 사용자의 리뷰입니다.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        self.stop()
        await self._disable_buttons(interaction)

        session = session_store.get(self.user_id)
        if not session or not session.fix_plan:
            await interaction.followup.send("❌ 세션이 만료되었습니다.")
            return

        await interaction.followup.send("🚀 GitHub에 브랜치를 생성하고 PR을 올리는 중...")

        try:
            github_token = key_store.get_gh_token(self.user_id)
            if not github_token:
                raise ValueError("GitHub 토큰이 등록되지 않았습니다. `/setup`을 다시 실행하세요.")
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
        await self._disable_buttons(interaction)


# ── Cog: 슬래시 커맨드 등록 ──────────────────────────────────────


class ReviewCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reporter = Reporter()

    @app_commands.command(name="setup", description="Anthropic API 키와 GitHub 토큰을 DM으로 등록합니다")
    async def setup_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔑 DM으로 안내를 보냈습니다.", ephemeral=True)
        try:
            dm = await interaction.user.create_dm()
            user_id = interaction.user.id

            def dm_check(m: discord.Message) -> bool:
                return m.author.id == user_id and isinstance(m.channel, discord.DMChannel)

            # ── Step 1: Anthropic API 키 ──────────────────────────
            await dm.send(
                "**PRism 설정 (1/2) — Anthropic API 키**\n\n"
                "Anthropic API 키를 이 채팅에 붙여넣기 해주세요.\n"
                "키는 `sk-ant-...` 형식입니다.\n"
                "<https://console.anthropic.com> 에서 발급받을 수 있습니다.\n\n"
                "⏰ 2분 안에 입력해 주세요.\n"
                "⚠️ 전송 후 보안을 위해 메시지를 직접 삭제해 주세요."
            )
            msg = await self.bot.wait_for("message", check=dm_check, timeout=120)
            api_key = msg.content.strip()

            if not api_key.startswith("sk-ant-"):
                await dm.send("❌ 올바른 Anthropic API 키 형식이 아닙니다 (`sk-ant-...`). `/setup`을 다시 실행하세요.")
                return

            await dm.send("🔍 Anthropic 키 유효성을 확인 중입니다...")
            ok, err = await LLMClient(api_key=api_key).validate()
            if not ok:
                await dm.send(f"❌ Anthropic 키 검증 실패: {err}\n올바른 키를 확인 후 `/setup`을 다시 실행하세요.")
                return

            key_store.set_key(user_id, api_key)
            await dm.send("✅ Anthropic API 키가 등록되었습니다.")

            # ── Step 2: GitHub Personal Access Token ─────────────
            await dm.send(
                "**PRism 설정 (2/2) — GitHub Personal Access Token**\n\n"
                "GitHub PAT를 이 채팅에 붙여넣기 해주세요.\n"
                "토큰은 `ghp_...` 또는 `github_pat_...` 형식입니다.\n"
                "<https://github.com/settings/tokens> 에서 발급받을 수 있습니다.\n"
                "필요 권한: `repo` (PR 생성용)\n\n"
                "⏰ 2분 안에 입력해 주세요.\n"
                "⚠️ 전송 후 보안을 위해 메시지를 직접 삭제해 주세요."
            )
            gh_msg = await self.bot.wait_for("message", check=dm_check, timeout=120)
            gh_token = gh_msg.content.strip()

            await dm.send("🔍 GitHub 토큰 유효성을 확인 중입니다...")
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        "https://api.github.com/user",
                        headers={"Authorization": f"Bearer {gh_token}"},
                    )
                if resp.status_code == 401:
                    await dm.send("❌ GitHub 토큰 검증 실패: 유효하지 않은 토큰입니다. `/setup`을 다시 실행하세요.")
                    return
                resp.raise_for_status()
            except httpx.HTTPError as e:
                await dm.send(f"❌ GitHub 토큰 검증 중 오류: {e}\n`/setup`을 다시 실행하세요.")
                return

            key_store.set_gh_token(user_id, gh_token)
            await dm.send(
                "✅ GitHub 토큰이 등록되었습니다.\n\n"
                "설정 완료! 이제 `/review` 명령어를 사용할 수 있습니다."
            )

        except TimeoutError:
            try:
                await interaction.user.send("⏰ 시간 초과. `/setup`을 다시 실행하세요.")
            except discord.Forbidden:
                pass
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ DM을 보낼 수 없습니다. Discord 설정에서 서버 멤버의 DM을 허용해 주세요.",
                ephemeral=True,
            )

    @app_commands.command(name="deletekey", description="등록된 API 키와 GitHub 토큰을 삭제합니다")
    async def deletekey_slash(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        had_api = key_store.has_key(user_id)
        had_gh = key_store.has_gh_token(user_id)
        key_store.delete_key(user_id)
        key_store.delete_gh_token(user_id)
        if had_api or had_gh:
            parts = []
            if had_api:
                parts.append("Anthropic API 키")
            if had_gh:
                parts.append("GitHub 토큰")
            await interaction.response.send_message(
                f"🗑️ {', '.join(parts)}가 삭제되었습니다.", ephemeral=True
            )
        else:
            await interaction.response.send_message("등록된 키가 없습니다.", ephemeral=True)

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

        api_key = key_store.get_key(user_id)
        if not api_key:
            await send_fn("❌ API 키가 등록되지 않았습니다. `/setup`을 먼저 실행하세요.")
            return

        owner, repo_name = parsed
        await send_fn(f"🔍 `{repo_url}` 분석을 시작합니다. 잠시 기다려 주세요...")

        try:
            reviewer = CodeReviewer(llm=LLMClient(api_key=api_key))
            result = await reviewer.review(repo_url)

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

            await send_fn(card_msg, file=md_file, view=ActionView(user_id, self.bot))

        except Exception as e:
            await send_fn(f"❌ 오류 발생: {e}")
