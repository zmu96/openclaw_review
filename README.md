# PRism

> Discord 봇 기반 AI 코드 리뷰 에이전트

GitHub 레포지토리 또는 PR URL만 입력하면 Claude AI가 코드를 분석하고,
사용자 승인 하에 수정 코드를 직접 PR로 올려주는 Human-in-the-Loop 코드 리뷰 봇입니다.

---

## 주요 기능

- **한 줄 리뷰 시작** — `/review <GitHub URL>` 하나로 전체 파이프라인 실행
- **종합 리뷰 카드** — 점수, 핵심 문제, 즉시 수정 항목을 Discord 메시지로 요약
- **3-버튼 인터랙션** — 리뷰 후 행동을 사용자가 직접 선택
  - `🔧 코드 수정 요청` — AI가 수정 계획 생성 후 PR 생성 여부 확인
  - `🔄 다시 계획해줘` — 피드백 입력 → 재계획 → 버튼 재표시 (루프 가능)
  - `📄 리뷰만 볼게요` — 세션 종료
- **자동 PR 생성** — 승인 시 브랜치 생성 → 코드 패치 → GitHub PR 자동 오픈
- **Human-in-the-Loop** — 모든 코드 변경은 사용자 승인 없이 절대 적용되지 않음
- **사용자별 키 관리** — Anthropic API 키와 GitHub 토큰을 Fernet 암호화로 개별 저장

---

## 기술 스택

| 구분 | 내용 |
|------|------|
| AI | Claude API (Anthropic) |
| 봇 프레임워크 | discord.py |
| 웹 서버 | FastAPI |
| Git 연동 | GitPython |
| 토큰 계산 | tiktoken |
| 암호화 | cryptography (Fernet) |
| 배포 | Render |
| 슬립 방지 | UptimeRobot |

---

## 시작하기

### 1. Discord 서버에 봇 초대

봇 초대 링크를 통해 서버에 PRism을 추가합니다.  
필요 권한: `Send Messages`, `Attach Files`, `Read Message History`

### 2. 키 등록 (`/setup`)

```
/setup
```

DM으로 2단계 등록을 진행합니다.

1. **Anthropic API 키** (`sk-ant-...`) — [console.anthropic.com](https://console.anthropic.com) 에서 발급
2. **GitHub Personal Access Token** (`ghp_...`) — [github.com/settings/tokens](https://github.com/settings/tokens) 에서 발급  
   필요 권한: `repo`

### 3. 코드 리뷰 시작 (`/review`)

```
/review https://github.com/owner/repo
```

GitHub 레포지토리 또는 PR URL을 입력하면 분석이 시작됩니다.

### 4. 키 삭제 (`/deletekey`)

```
/deletekey
```

등록된 Anthropic API 키와 GitHub 토큰을 모두 삭제합니다.

---

## 사용자 플로우

```
/review <URL>
    │
    ▼
AI 코드 분석 (구조 파악 → 청크별 리뷰 → 종합 요약)
    │
    ▼
Discord 리뷰 카드 + 상세 리뷰 .md 파일 전송
    │
    ├─[🔧 코드 수정 요청]──▶ 수정 계획 생성
    │                              │
    │                    ┌─[✅ 승인]──▶ 브랜치 생성 → 패치 적용 → PR 오픈
    │                    └─[❌ 거절]──▶ 세션 종료
    │
    ├─[🔄 다시 계획해줘]──▶ "피드백을 입력해주세요"
    │                              │
    │                        사용자 피드백 입력
    │                              │
    │                        재계획 후 리뷰 카드 재표시 (루프)
    │
    └─[📄 리뷰만 볼게요]──▶ 세션 종료
```

---

## 주의사항

- **API 키는 사용자가 직접 관리합니다.** PRism은 키를 서버 메모리에 암호화해 저장하며, 재시작 시 초기화됩니다. 재시작 후에는 `/setup`을 다시 실행해 주세요.
- **Render 무료 플랜**을 사용합니다. 일정 시간 요청이 없으면 서버가 슬립 상태에 진입할 수 있습니다. UptimeRobot으로 주기적 핑을 설정해 슬립을 방지하고 있습니다.
- PR 생성에는 `repo` 권한이 있는 GitHub PAT가 필요합니다. Fine-grained token의 경우 대상 레포에 대한 `Contents: Read/Write` 및 `Pull requests: Read/Write` 권한을 부여해 주세요.
