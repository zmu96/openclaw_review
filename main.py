"""
main.py — 애플리케이션 진입점

실행 방법:
  웹 서버:       python main.py --mode web
  디스코드 봇:   python main.py --mode discord
  둘 다 동시:    python main.py --mode both
"""

import argparse
import asyncio
from dotenv import load_dotenv

load_dotenv(override=True)


def run_web():
    import uvicorn
    from web.app import create_app

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)


async def run_discord():
    from bot.discord_bot import create_bot

    bot = create_bot()
    await bot.start_bot()


async def run_both():
    import uvicorn
    from web.app import create_app
    from bot.discord_bot import create_bot

    app = create_app()
    bot = create_bot()

    config = uvicorn.Config(app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)

    await asyncio.gather(
        server.serve(),
        bot.start_bot(),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Code Reviewer")
    parser.add_argument(
        "--mode",
        choices=["web", "discord", "both"],
        default="both",
        help="실행 모드 선택",
    )
    args = parser.parse_args()

    if args.mode == "web":
        run_web()
    elif args.mode == "discord":
        asyncio.run(run_discord())
    else:
        asyncio.run(run_both())
