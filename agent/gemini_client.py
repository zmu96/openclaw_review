"""
agent/gemini_client.py — LLM 클라이언트 (Claude → Gemini → Groq 순서로 시도)

우선순위:
  1. Claude API (ANTHROPIC_API_KEY 설정 시) — 가장 안정적, 한국어 품질 최고
  2. Gemini API (GEMINI_API_KEYS 설정 시) — 무료 티어, 다중 키 로테이션
  3. Groq API (GROQ_API_KEY 설정 시) — 최후 폴백
"""

import os
from google import genai
from google.genai.errors import ClientError


def _is_quota_error(exc: BaseException) -> bool:
    return isinstance(exc, ClientError) and ("429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc))


def _is_server_error(exc: BaseException) -> bool:
    """503 등 서버 측 일시 오류 — 재시도해도 의미 없으므로 즉시 중단."""
    return isinstance(exc, ClientError) and ("503" in str(exc) or "UNAVAILABLE" in str(exc))


class GeminiClient:
    def __init__(self):
        # ── 1순위: Claude ────────────────────────────────────────
        claude_key = os.getenv("ANTHROPIC_API_KEY")
        if claude_key and claude_key != "여기에_Claude_API_키_붙여넣기":
            import anthropic
            self._claude = anthropic.AsyncAnthropic(api_key=claude_key)
            self._claude_model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
        else:
            self._claude = None

        # ── 2순위: Gemini ────────────────────────────────────────
        raw = os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY")
        if not raw and self._claude is None:
            raise ValueError("ANTHROPIC_API_KEY 또는 GEMINI_API_KEYS 환경변수가 필요합니다.")
        self.api_keys = [k.strip() for k in raw.split(",") if k.strip()] if raw else []
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self._key_index = 0

        # ── 3순위: Groq ──────────────────────────────────────────
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            from groq import AsyncGroq
            self._groq = AsyncGroq(api_key=groq_key)
            self._groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        else:
            self._groq = None

    async def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        """프롬프트를 전송합니다. Claude → Gemini → Groq 순서로 시도합니다."""
        # 1순위: Claude
        if self._claude:
            return await self._generate_with_claude(prompt, temperature, max_tokens)

        # 2순위: Gemini (다중 키 로테이션)
        if self.api_keys:
            return await self._generate_with_gemini(prompt, temperature)

        # 3순위: Groq
        return await self._generate_with_groq(prompt)

    async def _generate_with_claude(self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        """Claude API로 생성. 스트리밍으로 타임아웃을 방지합니다."""
        try:
            async with self._claude.messages.stream(
                model=self._claude_model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                response = await stream.get_final_message()
            return next(b.text for b in response.content if b.type == "text")
        except Exception as e:
            print(f"[LLMClient] Claude 오류: {e}")
            if self.api_keys:
                print("[LLMClient] Gemini로 전환합니다.")
                return await self._generate_with_gemini(prompt)
            raise RuntimeError(f"Claude 오류 (폴백 없음): {e}") from e

    async def _generate_with_gemini(self, prompt: str, temperature: float = 0.7) -> str:
        """Gemini API로 생성. 할당량 초과 시 다음 키로 자동 전환합니다."""
        from google.genai import types as genai_types
        for attempt in range(len(self.api_keys)):
            client = genai.Client(api_key=self.api_keys[self._key_index])
            try:
                response = await client.aio.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(temperature=temperature),
                )
                return response.text
            except ClientError as e:
                if _is_server_error(e):
                    raise RuntimeError(
                        "Gemini 서버가 일시적으로 과부하 상태입니다. 잠시 후 다시 시도해 주세요."
                    ) from e
                if _is_quota_error(e):
                    next_index = (self._key_index + 1) % len(self.api_keys)
                    if next_index == 0 and attempt > 0:
                        print("[LLMClient] 모든 Gemini 키 소진 → Groq으로 전환")
                        return await self._generate_with_groq(prompt)
                    print(f"[LLMClient] Gemini 키 #{self._key_index + 1} 소진 → 키 #{next_index + 1}로 전환")
                    self._key_index = next_index
                else:
                    raise

        return await self._generate_with_groq(prompt)

    async def _generate_with_groq(self, prompt: str) -> str:
        """모든 상위 옵션 소진 시 Groq으로 폴백합니다."""
        if self._groq is None:
            raise RuntimeError(
                "사용 가능한 LLM이 없습니다. "
                "ANTHROPIC_API_KEY, GEMINI_API_KEYS, GROQ_API_KEY 중 하나를 설정하세요."
            )
        # 한국어 포함 시 토큰 소비가 많으므로 보수적으로 제한
        max_chars = 8_000
        if len(prompt) > max_chars:
            prompt = prompt[:max_chars] + "\n\n...(이하 생략, 토큰 한도로 인해 축소됨)"

        print(f"[LLMClient] Groq {self._groq_model}으로 생성합니다.")
        response = await self._groq.chat.completions.create(
            model=self._groq_model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
