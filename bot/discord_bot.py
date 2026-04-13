"""
bot/discord_bot.py — 디스코드 봇 설정 및 실행
"""

import os
import discord
from discord.ext import commands
from bot.commands import ReviewCommands


def create_bot() -> "CodeReviewBot":
    return CodeReviewBot()


class CodeReviewBot:
    def __init__(self):
        intents = discord.Intents.default()

        self.bot = commands.Bot(
            command_prefix="!",
            intents=intents,
            description="AI 코드 리뷰 봇",
        )
        self._setup_events()

    def _setup_events(self):
        @self.bot.event
        async def on_ready():
            print(f"[Discord] 봇 로그인: {self.bot.user} (ID: {self.bot.user.id})")
            await self.bot.add_cog(ReviewCommands(self.bot))
            await self.bot.tree.sync()

        @self.bot.event
        async def on_command_error(ctx, error):
            if isinstance(error, commands.MissingRequiredArgument):
                await ctx.send("사용법: `!review <GitHub URL>`")
            else:
                await ctx.send(f"오류가 발생했습니다: {error}")

    async def start_bot(self):
        token = os.getenv("DISCORD_BOT_TOKEN")
        if not token:
            raise ValueError("DISCORD_BOT_TOKEN 환경변수가 설정되지 않았습니다.")
        await self.bot.start(token)
