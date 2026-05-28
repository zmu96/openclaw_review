"""
agent/gemini_client.py — Anthropic Claude LLM 클라이언트
"""

import os
import anthropic

_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")


class LLMClient:
    def __init__(self, api_key: str):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
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
        try:
            await self.generate("ping", max_tokens=5)
            return True, ""
        except anthropic.AuthenticationError:
            return False, "유효하지 않은 API 키입니다."
        except anthropic.PermissionDeniedError:
            return False, "API 키에 접근 권한이 없습니다."
        except Exception as e:
            return False, f"검증 중 오류: {e}"
