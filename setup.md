# 설치 및 실행 가이드

## 요구 사항

- Python 3.11 이상
- Git
- Gemini API 키 ([Google AI Studio](https://aistudio.google.com)에서 발급)
- 디스코드 봇 토큰 ([Discord Developer Portal](https://discord.com/developers/applications))

---

## 로컬 실행

### 1. 의존성 설치

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
cp .env.example .env
# .env 파일을 열고 GEMINI_API_KEY, DISCORD_BOT_TOKEN 입력
```

### 3. 실행

```bash
# 웹 서버만
python main.py --mode web

# 디스코드 봇만
python main.py --mode discord

# 둘 다 동시 실행
python main.py --mode both
```

웹 UI: http://localhost:8000  
API 문서: http://localhost:8000/docs

---

## 디스코드 봇 사용법

서버에 봇을 초대한 뒤:

```
!review https://github.com/username/repository
```

또는 슬래시 커맨드:

```
/review url:https://github.com/username/repository
```

---

## 테스트 실행

```bash
pytest tests/ -v
```

---

## 배포 (Render)

1. GitHub에 이 레포를 push
2. [Render](https://render.com) → New Web Service → GitHub 레포 연결
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python main.py --mode web`
5. 환경변수 탭에서 `GEMINI_API_KEY` 등 입력
