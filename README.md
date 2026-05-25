# PRism

GitHub 레포지토리를 분석하여 AI 코드 리뷰 결과를 제공하는 에이전트입니다.  
Claude / Gemini / Groq 기반으로 동작하며, 디스코드 봇과 웹 UI 두 가지 인터페이스를 지원합니다.

---

## 기능

- GitHub URL 입력만으로 전체 프로젝트 자동 분석
- 파일 구조 및 아키텍처 파악
- 코드 품질 / 잠재적 버그 / 설계 개선 사항 리뷰
- 디스코드: Markdown 리포트 파일 첨부
- 웹 UI: HTML 리포트 브라우저 출력

## 빠른 시작

```bash
git clone <this-repo>
cd PRism
cp .env.example .env   # API 키 입력
pip install -r requirements.txt
python main.py --mode both
```

자세한 내용은 [docs/setup.md](docs/setup.md)를 참고하세요.

## 기술 스택

| 역할 | 기술 |
|------|------|
| AI | Claude / Gemini / Groq |
| 웹 백엔드 | FastAPI + Uvicorn |
| 디스코드 봇 | discord.py |
| 레포 분석 | GitPython |
| 배포 | Render |
