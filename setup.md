# 설치 및 실행 가이드

## 요구 사항

- Python 3.11 이상
- Git
- 디스코드 봇 토큰 ([Discord Developer Portal](https://discord.com/developers/applications))
- GitHub Personal Access Token (repo 스코프)
- 사용자별 Anthropic API 키 ([console.anthropic.com](https://console.anthropic.com))

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
# .env 파일을 열고 DISCORD_BOT_TOKEN, GITHUB_TOKEN, FERNET_KEY 입력
```

FERNET_KEY 생성:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
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

웹 UI: http://localhost:10000  
API 문서: http://localhost:10000/docs

---

## 디스코드 봇 사용법

서버에 봇을 초대한 뒤, **최초 1회 API 키 등록**:

```
/setup
```

봇이 DM으로 Anthropic API 키 입력을 안내합니다.  
등록 후 리뷰 명령어 사용:

```
/review url:https://github.com/username/repository
```

키 삭제:
```
/deletekey
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
4. Start Command: `python main.py --mode both`
5. Environment 탭에서 아래 변수 입력:
   - `DISCORD_BOT_TOKEN`
   - `GITHUB_TOKEN`
   - `FERNET_KEY`
   - `ANTHROPIC_API_KEY` (웹 UI 사용 시에만)
