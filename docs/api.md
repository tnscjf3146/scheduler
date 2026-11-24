# API

프론트(React)가 백엔드(FastAPI)에 보내는 요청 목록. 데이터는 [ERD](erd.md)를 따른다.

요청·응답의 자세한 형식은 따로 쓰지 않는다. FastAPI가 코드에서 자동으로 만드는 문서(`/docs`)를 본다. 이 문서에는 어떤 API가 있는지와, 자동 문서에 나오지 않는 WebSocket·MCP만 적는다.

## 공통

- 기본 경로: `/api`
- 요청·응답 본문은 JSON
- 오류는 `{"detail": "사용자에게 보여 줄 문장"}`

## REST

| 위젯 | 메서드 | 경로 | 설명 |
|---|---|---|---|
| 할 일 | GET | `/api/todos` | 전체 목록 (안 한 것, 날짜순) |
| 할 일 | POST | `/api/todos` | 추가. `title`, `due_at`(`YYYY-MM-DDTHH:MM`, 없어도 됨) |
| 할 일 | PATCH | `/api/todos/{id}` | `title`, `due_at`, `done` 중 보낸 것만 수정 |
| 할 일 | DELETE | `/api/todos/{id}` | 삭제 |
| 다가오는 일정 | GET | `/api/todos/upcoming` | 안 했고 날짜가 지나지 않은 할 일, 가까운 순 5개 |
| Agent | GET | `/api/agents` | 목록. `status`: `stopped` · `running` · `exited` |
| Agent | POST | `/api/agents` | 추가. `name`, `role`, `cli`(`claude` · `codex` · `shell`), `cwd` |
| Agent | POST | `/api/agents/{id}/restart` | 터미널 세션 종료. 다음에 열면 새로 시작 |
| Agent | DELETE | `/api/agents/{id}` | 삭제 (세션도 종료) |
| 결재 대기 | GET | `/api/approvals?status=pending` | 결재 문서 목록 |
| 결재 대기 | GET | `/api/approvals/{id}` | 결재 문서 |
| 결재 대기 | POST | `/api/approvals/{id}/decision` | `decision`(`approved` · `rejected`), `reason`(반려 시 필수) |
| 메일 검토 | GET | `/api/mail/accounts` | 연결된 메일 계정 |
| 메일 검토 | POST | `/api/mail/accounts` | 계정 연결. `provider`(`gmail` · `naver` · `custom`), `email`, `password`, 직접 입력이면 IMAP·SMTP 서버 |
| 메일 검토 | DELETE | `/api/mail/accounts/{id}` | 연결 끊기 (받아 둔 메일도 삭제) |
| 메일 검토 | GET | `/api/mail/messages` | 받은 메일 목록 (요약 제목 포함) |
| 메일 검토 | GET | `/api/mail/messages/{id}` | 메일 상세: 요약, 원문, 답장 초안 |
| 메일 검토 | POST | `/api/mail/messages/{id}/reply` | 답장 전송. 사용자가 전송 버튼을 눌렀을 때만 부른다 |
| 메일 검토 | POST | `/api/mail/sync` | 새 메일 확인을 바로 실행 |

## WebSocket: 에이전트 터미널

`/api/agents/{id}/terminal?cols=100&rows=30`

- 연결하면 세션이 없을 때 새로 시작하고, 지금까지의 출력(최대 약 25만 자)을 먼저 보낸다.
- 화면 → 서버 (JSON)
  - `{"type": "input", "data": "..."}`: 키 입력
  - `{"type": "resize", "cols": 120, "rows": 40}`: 터미널 크기 변경
- 서버 → 화면: 터미널 출력 텍스트 그대로

## MCP: 결재 올리기

에이전트의 CLI가 부르는 도구. 앱이 에이전트를 시작할 때 연결 정보를 넣어 준다 (Claude Code는 `--mcp-config`, Codex는 `-c mcp_servers.scheduler.url=...`).

- 주소: `POST /mcp/{agent_id}` (Streamable HTTP, JSON 응답만)

| 도구 | 입력 | 결과 |
|---|---|---|
| `submit_approval` | `title`, `decision`, `background`(선택), `attachments`(선택, 파일 경로 목록) | `{"id": ..., "status": "pending"}` |
| `get_approval` | `id` | `{"id", "status", "reason", "decided_at"}`. 에이전트는 이걸로 결과를 확인한다 |
