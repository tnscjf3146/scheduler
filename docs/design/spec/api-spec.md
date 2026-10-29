# API 명세 (MVP)

웹과 앱이 함께 쓰는 REST API. 기능은 [기능 명세](feature-spec.md), 규칙은 [정책](../policy/policy.md), 데이터는 [ERD](../erd.md)를 따른다. 표의 ID는 기능 명세의 기능 ID다.

## 1. 공통 규칙

### 기본
- 기본 경로: `/api` (로컬 `http://localhost:8080/api`)
- 요청 · 응답 본문은 JSON (`Content-Type: application/json`), 문자셋 UTF-8.
- JSON 필드 이름은 `camelCase`. 값이 없으면 필드를 빼지 않고 `null`로 보낸다.
- 경로는 소문자 `kebab-case`, 복수형 명사 (`/issue-types`). 동사가 필요한 동작만 끝에 붙인다 (`/start`, `/complete`, `/move`).

### 식별자
| 대상 | 경로에 쓰는 값 | 예 |
|---|---|---|
| 프로젝트 | 프로젝트 키 | `/projects/SCH` |
| 이슈 | 이슈 키 | `/issues/SCH-12` |
| 그 외 | 숫자 id | `/projects/SCH/sprints/3` |

- 프로젝트 키 · 이슈 키는 바뀌지 않아 URL에 그대로 써도 안전하고, 사람이 읽을 수 있다.

### 날짜 · 시간
- 시각: ISO-8601 UTC. 예: `"2026-10-30T05:12:00Z"`. 화면에서 기기 시간대로 바꿔 보여준다.
- 날짜(기한, 스프린트 기간): `"2026-11-15"`.

### HTTP 메서드 · 상태 코드
| 메서드 | 쓰임 | 성공 |
|---|---|---|
| `GET` | 조회 | `200` |
| `POST` | 생성, 동작 실행 | `201` (생성), `200` (동작) |
| `PATCH` | 일부 필드 수정. 보낸 필드만 바뀐다 | `200` |
| `DELETE` | 삭제 | `204` (본문 없음) |

| 상태 코드 | 뜻 |
|---|---|
| `400` | 요청 값이 잘못됨 (검증 실패, 규칙 위반) |
| `401` | 로그인 필요, 토큰 만료 · 잘못됨 |
| `403` | 프로젝트 멤버지만 권한 없음 (예: 멤버가 스프린트 시작) |
| `404` | 없음. **프로젝트 멤버가 아닌 사람이 프로젝트 · 이슈를 조회해도 404** (존재 여부를 숨긴다) |
| `409` | 현재 상태와 충돌 (중복, 마지막 관리자, 진행 중 스프린트 있음 …) |
| `500` | 서버 오류 |

### 인증 (JWT)
- 로그인하면 **액세스 토큰**과 **리프레시 토큰**을 받는다.
- 인증이 필요한 요청은 헤더에 액세스 토큰을 넣는다: `Authorization: Bearer {accessToken}`
- `/auth/signup`, `/auth/login`, `/auth/refresh` 외의 모든 API는 인증이 필요하다.

| 토큰 | 유효 기간 | 저장 (웹) | 저장 (앱) |
|---|---|---|---|
| 액세스 토큰 | 30분 | 메모리 (변수) | 메모리 |
| 리프레시 토큰 | 14일 | **HttpOnly 쿠키** (서버가 설정, JS로 못 읽음) | DataStore (암호화 저장) |

```
요청 → 401 TOKEN_EXPIRED → POST /auth/refresh → 새 토큰 받기 → 원래 요청 재시도
                                  └ 실패(401) → 로그인 화면으로
```

- 리프레시 토큰은 **한 번 쓰면 바뀐다** (재발급할 때마다 새 리프레시 토큰을 주고 이전 것은 무효).
- 서버는 리프레시 토큰의 해시만 저장한다 (`refresh_tokens` 테이블). 로그아웃 · 비밀번호 변경 · 탈퇴하면 지운다.

### 페이지네이션
목록 API는 `page`(0부터), `size`(기본 50, 최대 100)를 받는다.

```json
{
  "items": [ … ],
  "page": 0,
  "size": 50,
  "totalCount": 132,
  "hasNext": true
}
```

### 에러 응답
모든 에러는 같은 모양이다 ([백엔드 컨벤션](../../convention/backend-convention.md#에러-처리)).

```json
{
  "code": "VALIDATION_FAILED",
  "message": "입력값을 확인해 주세요.",
  "fieldErrors": [
    { "field": "title", "reason": "제목은 1~255자여야 합니다." }
  ],
  "retryAfterSeconds": null
}
```

- `code`로 분기하고, `message`는 화면에 그대로 보여줄 수 있는 문장이다.
- `fieldErrors`는 `VALIDATION_FAILED`일 때만 채운다. `retryAfterSeconds`는 MVP에서 항상 `null`이다.
- 코드 목록: [9. 에러 코드](#9-에러-코드)

## 2. 공통 응답 모델

여러 API가 같이 쓰는 모양. 아래 예시에서 이름만 적고 다시 풀어 쓰지 않는다.

```jsonc
// UserSummary
{ "id": 7, "name": "김철수", "email": "kim@example.com" }

// StatusSummary
{ "id": 2, "name": "진행 중", "category": "IN_PROGRESS" }

// IssueTypeSummary
{ "id": 3, "name": "버그", "level": "STANDARD" }

// SprintSummary
{ "id": 3, "name": "SCH 스프린트 3", "state": "ACTIVE", "startDate": "2026-10-27", "endDate": "2026-11-09" }

// IssueSummary — 목록 · 보드 · 백로그 카드
{
  "key": "SCH-12",
  "title": "로그인 버튼이 안 눌림",
  "type": IssueTypeSummary,
  "status": StatusSummary,
  "priority": "HIGH",
  "assignee": UserSummary | null,
  "dueDate": "2026-11-05" | null,
  "epic": { "key": "SCH-3", "title": "로그인 기능" } | null,
  "labels": ["frontend", "urgent"],
  "subtaskCount": 2
}
```

- 탈퇴한 사용자는 `UserSummary` 대신 `null`이다. 화면에서 "알 수 없는 사용자"로 보여준다.

## 3. 인증 · 사용자 (USER)

| 메서드 | 경로 | ID | 권한 | 설명 |
|---|---|---|---|---|
| `POST` | `/auth/signup` | USER-1 | 누구나 | 회원가입 |
| `POST` | `/auth/login` | USER-2 | 누구나 | 로그인 → 토큰 발급 |
| `POST` | `/auth/refresh` | USER-2 | 누구나 | 토큰 재발급 |
| `POST` | `/auth/logout` | USER-2 | 로그인 | 리프레시 토큰 무효화 |
| `GET` | `/users/me` | USER-3 | 로그인 | 내 정보 |
| `PATCH` | `/users/me` | USER-3 | 로그인 | 이름 변경 |
| `PATCH` | `/users/me/password` | USER-3 | 로그인 | 비밀번호 변경 |
| `DELETE` | `/users/me` | USER-4 | 로그인 | 탈퇴 |

### `POST /auth/signup`
```json
// 요청
{ "email": "kim@example.com", "password": "abcd1234", "name": "김철수" }
// 201 응답
UserSummary
```
- 에러: `VALIDATION_FAILED`, `EMAIL_DUPLICATED`

### `POST /auth/login`
```json
// 요청
{ "email": "kim@example.com", "password": "abcd1234" }
// 200 응답
{
  "accessToken": "eyJ…",
  "accessTokenExpiresAt": "2026-10-30T05:42:00Z",
  "refreshToken": "eyJ…",
  "user": UserSummary
}
```
- 웹: 리프레시 토큰을 `Set-Cookie: refreshToken=…; HttpOnly; Secure; SameSite=Strict; Path=/api/auth`로도 내려준다. 웹은 본문의 `refreshToken`을 버린다.
- 에러: `LOGIN_FAILED` (이메일 · 비밀번호 중 무엇이 틀렸는지 구분하지 않는다)

### `POST /auth/refresh`
```json
// 요청 (앱). 웹은 본문 없이 보내면 쿠키를 쓴다
{ "refreshToken": "eyJ…" }
// 200 응답: /auth/login과 같은 모양 (새 리프레시 토큰 포함)
```
- 에러: `INVALID_REFRESH_TOKEN` (만료, 이미 쓴 토큰, 로그아웃된 토큰)

### `POST /auth/logout`
- 요청: `/auth/refresh`와 같이 리프레시 토큰. 응답 `204`. 웹은 쿠키를 지운다.

### `PATCH /users/me/password`
```json
{ "currentPassword": "abcd1234", "newPassword": "efgh5678" }
```
- 성공하면 이 사용자의 **모든 리프레시 토큰을 지운다** (다른 기기 로그아웃). 응답은 새 토큰 (`/auth/login`과 같은 모양).
- 에러: `PASSWORD_MISMATCH`, `VALIDATION_FAILED`

### `DELETE /users/me`
```json
// 요청
{ "password": "abcd1234" }
```
- 에러: `PASSWORD_MISMATCH`, `WITHDRAW_BLOCKED` (리드이거나 마지막 관리자인 프로젝트가 있음)

```json
// 409 WITHDRAW_BLOCKED
{
  "code": "WITHDRAW_BLOCKED",
  "message": "리드이거나 마지막 관리자인 프로젝트가 있어 탈퇴할 수 없습니다.",
  "fieldErrors": [],
  "retryAfterSeconds": null,
  "projects": [{ "key": "SCH", "name": "스케줄러", "reason": "LEAD" }]
}
```

## 4. 프로젝트 · 멤버 (PRJ)

| 메서드 | 경로 | ID | 권한 | 설명 |
|---|---|---|---|---|
| `GET` | `/projects` | PRJ-2 | 로그인 | 내가 멤버인 프로젝트 목록 |
| `POST` | `/projects` | PRJ-1 | 로그인 | 프로젝트 생성 |
| `GET` | `/projects/{key}` | | 멤버 | 프로젝트 정보 |
| `PATCH` | `/projects/{key}` | PRJ-3 | 관리자 | 이름, 설명, 리드, 스프린트 사용 변경 |
| `DELETE` | `/projects/{key}` | PRJ-4 | 관리자 | 프로젝트 삭제 |
| `GET` | `/projects/{key}/members` | | 멤버 | 멤버 목록 (담당자 · 멘션 선택에도 씀) |
| `POST` | `/projects/{key}/members` | PRJ-5 | 관리자 | 멤버 추가 |
| `PATCH` | `/projects/{key}/members/{userId}` | PRJ-6 | 관리자 | 역할 변경 |
| `DELETE` | `/projects/{key}/members/{userId}` | PRJ-6 | 관리자 | 내보내기 |
| `DELETE` | `/projects/{key}/members/me` | PRJ-7 | 멤버 | 나가기 |

### `POST /projects`
```json
// 요청
{ "name": "스케줄러", "key": "SCH", "description": null, "sprintEnabled": true }
// 201 응답 (= GET /projects/{key})
{
  "key": "SCH",
  "name": "스케줄러",
  "description": null,
  "lead": UserSummary,
  "sprintEnabled": true,
  "myRole": "ADMIN",
  "createdAt": "2026-10-30T05:12:00Z"
}
```
- 기본 상태 3개, 기본 이슈 유형 5개를 함께 만든다.
- 에러: `PROJECT_KEY_INVALID`, `PROJECT_KEY_DUPLICATED`

### `PATCH /projects/{key}`
```json
{ "name": "스케줄러 앱", "leadUserId": 9, "sprintEnabled": false }
```
- `key`는 바꿀 수 없다 (보내면 무시하지 않고 `VALIDATION_FAILED`).
- 에러: `LEAD_MUST_BE_ADMIN`, `SPRINT_ACTIVE_CANNOT_DISABLE`

### `POST /projects/{key}/members`
```json
// 요청
{ "email": "lee@example.com", "role": "MEMBER" }
// 201 응답
{ "user": UserSummary, "role": "MEMBER", "joinedAt": "2026-10-30T05:12:00Z" }
```
- 에러: `USER_NOT_FOUND` (가입하지 않은 이메일), `MEMBER_ALREADY_EXISTS`

### 역할 변경 · 내보내기 · 나가기
- 에러: `LAST_ADMIN` (마지막 관리자를 멤버로 바꾸거나 내보내거나 나감), `LEAD_CANNOT_LEAVE` (리드를 내보내거나 리드가 나감)

## 5. 상태 · 이슈 유형 (WF)

| 메서드 | 경로 | ID | 권한 | 설명 |
|---|---|---|---|---|
| `GET` | `/projects/{key}/statuses` | WF-1 | 멤버 | 상태 목록 (`position` 순) |
| `POST` | `/projects/{key}/statuses` | WF-2 | 관리자 | 상태 추가 |
| `PATCH` | `/projects/{key}/statuses/{id}` | WF-3 | 관리자 | 이름 · 순서 변경 |
| `DELETE` | `/projects/{key}/statuses/{id}` | WF-4 | 관리자 | 상태 삭제 |
| `GET` · `POST` | `/projects/{key}/issue-types` | WF-5 | 멤버 · 관리자 | 이슈 유형 목록 · 추가 |
| `PATCH` · `DELETE` | `/projects/{key}/issue-types/{id}` | WF-5 | 관리자 | 이슈 유형 수정 · 삭제 |

```json
// POST /projects/SCH/statuses
{ "name": "코드 리뷰", "category": "IN_PROGRESS" }
// 201 응답
{ "id": 4, "name": "코드 리뷰", "category": "IN_PROGRESS", "position": 3, "issueCount": 0 }

// PATCH /projects/SCH/statuses/4  (순서 변경)
{ "position": 1 }
```

- 이슈 유형은 `category` 대신 `level`(`EPIC` · `STANDARD` · `SUBTASK`)을 보낸다.
- `category` · `level`은 PATCH로 바꿀 수 없다.
- 삭제할 때 그 상태 · 유형의 이슈가 있으면 옮길 대상을 쿼리로 준다: `DELETE /projects/SCH/statuses/4?moveTo=2`
- 에러: `STATUS_NAME_DUPLICATED`, `LAST_STATUS_IN_CATEGORY`, `STATUS_HAS_ISSUES` (이슈가 있는데 `moveTo` 없음), `ISSUE_TYPE_NAME_DUPLICATED`, `LAST_ISSUE_TYPE_IN_LEVEL`, `ISSUE_TYPE_HAS_ISSUES`, `ISSUE_TYPE_LEVEL_MISMATCH` (다른 계층의 유형으로 옮기려 함)

## 6. 이슈 (ISSUE, SEARCH, BOARD, BACKLOG)

| 메서드 | 경로 | ID | 권한 | 설명 |
|---|---|---|---|---|
| `GET` | `/projects/{key}/issues` | SEARCH-1, 2 | 멤버 | 이슈 목록 · 검색 |
| `POST` | `/projects/{key}/issues` | ISSUE-1 | 멤버 | 이슈 생성 |
| `GET` | `/issues/{issueKey}` | ISSUE-2, SEARCH-3 | 멤버 | 이슈 상세 |
| `PATCH` | `/issues/{issueKey}` | ISSUE-3, 4, 6 | 멤버 | 이슈 수정 (상태 · 레이블 포함) |
| `DELETE` | `/issues/{issueKey}` | ISSUE-5 | 관리자 · 보고자 | 이슈 삭제 |
| `POST` | `/issues/{issueKey}/move` | BOARD-2, BACKLOG-2, 3 | 멤버 | 드래그: 순서 · 상태 · 스프린트 변경 |
| `POST` | `/projects/{key}/issues/bulk-move` | BACKLOG-3 | 멤버 | 여러 이슈를 스프린트(또는 백로그)로 |
| `GET` | `/projects/{key}/board` | BOARD-1, 3 | 멤버 | 보드 화면 데이터 |
| `GET` | `/projects/{key}/backlog` | BACKLOG-1 | 멤버 | 백로그 화면 데이터 |
| `GET` | `/projects/{key}/labels` | ISSUE-6 | 멤버 | 레이블 자동완성 |

### `GET /projects/{key}/issues`
| 쿼리 | 예 | 설명 |
|---|---|---|
| `q` | `로그인` | 키 · 제목 검색 |
| `statusId` | `2,4` | 쉼표로 여러 개 |
| `category` | `TODO,IN_PROGRESS` | 상태 분류. "미완료" = `TODO,IN_PROGRESS` |
| `typeId` | `3` | |
| `assignee` | `7`, `me`, `none` | `none` = 미배정 |
| `priority` | `HIGH,HIGHEST` | |
| `label` | `urgent` | |
| `sprint` | `3`, `active`, `backlog` | |
| `overdue` | `true` | 기한 지난 미완료 |
| `sort` | `createdAt,desc` | `createdAt`, `updatedAt`, `priority`, `dueDate`, `rank` |
| `page`, `size` | | 페이지네이션 |

- 응답: `IssueSummary`의 페이지.
- 대시보드 위젯을 누르면 이 쿼리로 목록을 연다 (예: `?assignee=7&category=TODO,IN_PROGRESS`).

### `POST /projects/{key}/issues`
```json
// 요청
{
  "typeId": 3,
  "title": "로그인 버튼이 안 눌림",
  "description": "## 재현 방법\n1. …",
  "assigneeId": 7,
  "priority": "HIGH",
  "labels": ["frontend", "urgent"],
  "dueDate": "2026-11-05",
  "parentKey": "SCH-3",
  "sprintId": null,
  "statusId": null
}
```
- 필수는 `typeId`, `title`. 나머지는 빼거나 `null`이면 기본값 ([기능 명세: 이슈 필드](feature-spec.md#이슈-필드)).
- `statusId`: 보드 열에서 빠른 생성할 때만 보낸다.
- `labels`: 이름 목록. 없는 이름은 새로 만든다.
- 201 응답: 이슈 상세 (아래 `GET /issues/{issueKey}`와 같은 모양).
- 에러: `INVALID_PARENT` (계층 규칙 위반), `NOT_PROJECT_MEMBER` (담당자가 멤버 아님), `EPIC_NOT_ALLOWED_IN_SPRINT`, `SPRINT_CLOSED`, `SPRINT_DISABLED`

### `GET /issues/{issueKey}`
```json
{
  "key": "SCH-12",
  "projectKey": "SCH",
  "title": "로그인 버튼이 안 눌림",
  "description": "## 재현 방법\n1. …",
  "type": IssueTypeSummary,
  "status": StatusSummary,
  "priority": "HIGH",
  "assignee": UserSummary,
  "reporter": UserSummary,
  "parent": { "key": "SCH-3", "title": "로그인 기능", "type": IssueTypeSummary } ,
  "sprint": SprintSummary,
  "labels": ["frontend", "urgent"],
  "dueDate": "2026-11-05",
  "children": [IssueSummary],
  "progress": { "done": 1, "total": 2 },
  "resolvedAt": null,
  "createdAt": "2026-10-30T05:12:00Z",
  "updatedAt": "2026-10-30T06:00:00Z",
  "canDelete": true
}
```
- `children`: 에픽이면 아래 이슈, 일반 이슈면 하위 작업. `progress`는 에픽일 때만 (아니면 `null`).
- `canDelete`: 화면에서 삭제 메뉴를 보여줄지 (관리자 또는 보고자).

### `PATCH /issues/{issueKey}`
보낸 필드만 바꾼다. 상세 화면에서 필드 하나를 고칠 때마다 그 필드만 보낸다.

```json
{ "statusId": 4 }
{ "assigneeId": null }
{ "labels": ["frontend"] }
{ "parentKey": "SCH-5" }
```
- 바꿀 수 있는 필드: `typeId`(같은 계층 안에서만), `title`, `description`, `statusId`, `priority`, `assigneeId`, `parentKey`, `sprintId`, `labels`(전체 교체), `dueDate`
- 상태를 바꾸면 새 열의 맨 아래로 간다 (순서까지 정하려면 `/move`).
- 응답: 이슈 상세.
- 에러: `POST`와 같음 + `ISSUE_TYPE_LEVEL_MISMATCH`, `SUBTASK_SPRINT_FOLLOWS_PARENT`

### `POST /issues/{issueKey}/move`
보드 · 백로그에서 카드를 끌어다 놓았을 때. 서버가 앞뒤 이슈 사이의 rank를 계산한다.

```json
{
  "statusId": 2,
  "sprintId": 3,
  "afterKey": "SCH-7",
  "beforeKey": "SCH-9"
}
```
| 필드 | 뜻 |
|---|---|
| `statusId` | 다른 열로 옮겼을 때만 (보드) |
| `sprintId` | 다른 스프린트 · 백로그로 옮겼을 때만 (백로그). 백로그는 `null`을 명시 |
| `afterKey` | 놓은 자리 바로 **위** 이슈. 맨 위면 `null` |
| `beforeKey` | 놓은 자리 바로 **아래** 이슈. 맨 아래면 `null` |

- 응답: `IssueSummary`. 하위 작업은 부모를 따라 스프린트가 함께 바뀐다.

### `POST /projects/{key}/issues/bulk-move`
```json
{ "issueKeys": ["SCH-4", "SCH-8", "SCH-11"], "sprintId": 3 }
```
- 고른 이슈를 그 스프린트(`null`이면 백로그) 맨 아래로, 고른 순서대로 옮긴다. 응답 `204`.

### `GET /projects/{key}/board`
쿼리는 이슈 목록의 필터(`assignee`, `typeId`, `priority`, `label`)를 그대로 받는다.

```json
{
  "sprintEnabled": true,
  "sprint": SprintSummary | null,
  "columns": [
    { "status": StatusSummary, "issues": [IssueSummary] }
  ]
}
```
- 스프린트 사용 켬: 진행 중 스프린트의 이슈. 진행 중 스프린트가 없으면 `sprint: null`, 열은 비어 있다.
- 스프린트 사용 끔: 모든 이슈. 완료 분류 열은 최근 14일 안에 완료된 이슈만.
- 에픽은 넣지 않는다. 각 열은 `rank` 순.

### `GET /projects/{key}/backlog`
```json
{
  "activeSprint": { "sprint": SprintSummary, "issues": [IssueSummary] } | null,
  "futureSprints": [{ "sprint": SprintSummary, "issues": [IssueSummary] }],
  "backlog": [IssueSummary]
}
```
- 에픽 · 완료 이슈는 넣지 않는다. 하위 작업은 부모의 `subtaskCount`로만 보여주고 목록에서 뺀다.
- 스프린트 사용이 꺼진 프로젝트면 `SPRINT_DISABLED`.

### `GET /projects/{key}/labels?q=fr`
```json
["frontend", "free-tier"]
```
- 이슈에 붙어 있는 레이블만, 이름순 최대 20개.

## 7. 스프린트 (SPRINT)

모두 스프린트 사용이 켜진 프로젝트에서만. 꺼져 있으면 `SPRINT_DISABLED`.

| 메서드 | 경로 | ID | 권한 | 설명 |
|---|---|---|---|---|
| `GET` | `/projects/{key}/sprints?state=CLOSED` | SPRINT-6 | 멤버 | 스프린트 목록 (상태 필터) |
| `GET` | `/projects/{key}/sprints/{id}` | SPRINT-4 | 멤버 | 스프린트 하나 (완료 · 남은 이슈 수 포함) |
| `POST` | `/projects/{key}/sprints` | SPRINT-1 | 멤버 | 스프린트 생성 |
| `PATCH` | `/projects/{key}/sprints/{id}` | SPRINT-3 | 멤버 | 이름 · 목표 · 기간 수정 |
| `POST` | `/projects/{key}/sprints/{id}/start` | SPRINT-2 | 관리자 | 시작 |
| `POST` | `/projects/{key}/sprints/{id}/complete` | SPRINT-4 | 관리자 | 완료 |
| `DELETE` | `/projects/{key}/sprints/{id}` | SPRINT-5 | 관리자 | 삭제 (계획 상태만) |
| `GET` | `/projects/{key}/sprints/{id}/issues` | SPRINT-6 | 멤버 | 스프린트의 이슈 (지난 스프린트 보기) |

### `POST /projects/{key}/sprints`
```json
// 요청 (name 생략 시 "SCH 스프린트 {n}")
{ "name": null, "goal": null }
// 201 응답
{ "id": 4, "name": "SCH 스프린트 4", "goal": null, "state": "FUTURE", "startDate": null, "endDate": null, "completedAt": null, "issueCount": 0 }
```

### `POST /projects/{key}/sprints/{id}/start`
```json
{ "startDate": "2026-10-30", "endDate": "2026-11-13", "goal": "로그인 · 회원가입 완성" }
```
- 에러: `SPRINT_ALREADY_ACTIVE` (진행 중 스프린트 있음), `SPRINT_NOT_FUTURE`, `INVALID_SPRINT_DATES`

### `POST /projects/{key}/sprints/{id}/complete`
```json
// 요청: 남은 이슈를 보낼 곳. null = 백로그
{ "moveToSprintId": 5 }
// 200 응답
{ "sprint": SprintSummary, "doneCount": 8, "movedCount": 3 }
```
- 화면은 먼저 `GET …/sprints/{id}`로 완료 · 남은 이슈 수를 보여준 뒤 이 API를 부른다.
- 에러: `SPRINT_NOT_ACTIVE`, `SPRINT_NOT_FUTURE` (`moveToSprintId`가 계획 상태가 아님)

### `DELETE /projects/{key}/sprints/{id}`
- 그 스프린트의 이슈는 백로그로 돌아간다. 에러: `SPRINT_NOT_FUTURE`

## 8. 댓글 · 알림 · 대시보드

### 댓글 (CMT)

| 메서드 | 경로 | ID | 권한 | 설명 |
|---|---|---|---|---|
| `GET` | `/issues/{issueKey}/comments` | CMT-1 | 멤버 | 댓글 목록 (오래된 순, 페이지네이션) |
| `POST` | `/issues/{issueKey}/comments` | CMT-1 | 멤버 | 댓글 작성 |
| `PATCH` | `/issues/{issueKey}/comments/{id}` | CMT-2 | 작성자 | 댓글 수정 |
| `DELETE` | `/issues/{issueKey}/comments/{id}` | CMT-2 | 작성자 · 관리자 | 댓글 삭제 |

```json
// POST 요청: 멘션은 @{userId}로 보낸다
{ "content": "@{9} 확인 부탁드려요" }
// 201 응답
{
  "id": 31,
  "author": UserSummary,
  "content": "@{9} 확인 부탁드려요",
  "mentions": [UserSummary],
  "createdAt": "2026-10-30T05:12:00Z",
  "edited": false
}
```
- 화면은 `mentions`를 보고 `@{9}`를 `@이민수`로 바꿔 보여준다.
- 에러: `NOT_PROJECT_MEMBER` (멘션한 사람이 멤버 아님)

### 알림 (NOTI)

| 메서드 | 경로 | ID | 설명 |
|---|---|---|---|
| `GET` | `/notifications` | NOTI-1 | 내 알림 (최신순, 페이지네이션) |
| `GET` | `/notifications/unread-count` | NOTI-2 | 안 읽은 알림 수 → `{ "count": 3 }` |
| `POST` | `/notifications/{id}/read` | NOTI-3 | 읽음 처리 |
| `POST` | `/notifications/read-all` | NOTI-3 | 모두 읽음 |

```json
// GET /notifications 의 items 하나
{
  "id": 120,
  "type": "COMMENTED",
  "actor": UserSummary,
  "issue": { "key": "SCH-12", "title": "로그인 버튼이 안 눌림" },
  "read": false,
  "createdAt": "2026-10-30T05:12:00Z"
}
```
- 알림 문구는 화면이 `type`으로 만든다 ([유저플로우: 알림](../user-flow/user-flow.md#6-알림-noti-13)).
- 안 읽은 수는 화면이 30초마다, 그리고 앱이 앞으로 올 때 다시 조회한다 (MVP는 실시간 푸시 없음).

### 대시보드 (DASH)

| 메서드 | 경로 | ID | 설명 |
|---|---|---|---|
| `GET` | `/projects/{key}/dashboard?tz=Asia/Seoul` | DASH-1~8 | 위젯 데이터 한 번에 |

```json
{
  "myIssues": [IssueSummary],
  "byCategory": { "TODO": 12, "IN_PROGRESS": 5, "DONE": 30 },
  "byStatus": [{ "status": StatusSummary, "count": 5 }],
  "byAssignee": [{ "assignee": UserSummary | null, "count": 4 }],
  "byPriority": { "HIGHEST": 1, "HIGH": 4, "MEDIUM": 9, "LOW": 3, "LOWEST": 0 },
  "overdue": [IssueSummary],
  "createdVsResolved": [{ "date": "2026-10-01", "created": 3, "resolved": 1 }],
  "activeSprint": { "sprint": SprintSummary, "done": 6, "total": 14, "daysLeft": 4 } | null,
  "epics": [{ "key": "SCH-3", "title": "로그인 기능", "done": 3, "total": 5 }]
}
```
- `tz`: 생성 · 해결 추이를 날짜로 나눌 시간대 (기기 시간대). 없으면 UTC.
- `myIssues`, `overdue`는 최대 10개. 더 보기는 이슈 목록 API로.
- 에픽은 이슈 수 집계에서 뺀다 ([정책: 대시보드](../policy/policy.md#대시보드)).

## 9. 에러 코드

### 공통

| code | HTTP | 언제 |
|---|---|---|
| `VALIDATION_FAILED` | 400 | 요청 값 검증 실패. `fieldErrors`에 필드별 이유 |
| `UNAUTHORIZED` | 401 | 토큰 없음 · 잘못됨 |
| `TOKEN_EXPIRED` | 401 | 액세스 토큰 만료 → `/auth/refresh` |
| `FORBIDDEN` | 403 | 멤버지만 권한 없음 |
| `NOT_FOUND` | 404 | 없음, 또는 멤버가 아닌 프로젝트 · 이슈 |
| `INTERNAL_ERROR` | 500 | 서버 오류 (내용은 로그에만) |

### 기능별

| code | HTTP | 언제 |
|---|---|---|
| `EMAIL_DUPLICATED` | 409 | 이미 가입한 이메일 |
| `LOGIN_FAILED` | 401 | 이메일 또는 비밀번호 틀림 |
| `INVALID_REFRESH_TOKEN` | 401 | 리프레시 토큰 만료 · 사용됨 · 무효 |
| `PASSWORD_MISMATCH` | 400 | 현재 비밀번호 틀림 (비밀번호 변경, 탈퇴) |
| `WITHDRAW_BLOCKED` | 409 | 리드 · 마지막 관리자인 프로젝트가 있어 탈퇴 불가 |
| `PROJECT_KEY_INVALID` | 400 | 키 형식 오류 |
| `PROJECT_KEY_DUPLICATED` | 409 | 이미 쓰는 키 |
| `LEAD_MUST_BE_ADMIN` | 400 | 관리자가 아닌 사람을 리드로 지정 |
| `USER_NOT_FOUND` | 404 | 멤버 추가: 가입하지 않은 이메일 |
| `MEMBER_ALREADY_EXISTS` | 409 | 이미 멤버 |
| `LAST_ADMIN` | 409 | 마지막 관리자를 바꾸거나 내보내거나 나감 |
| `LEAD_CANNOT_LEAVE` | 409 | 리드를 내보내거나 리드가 나감 |
| `NOT_PROJECT_MEMBER` | 400 | 담당자 · 멘션 대상이 프로젝트 멤버 아님 |
| `STATUS_NAME_DUPLICATED` | 409 | 같은 이름의 상태 있음 |
| `LAST_STATUS_IN_CATEGORY` | 409 | 분류의 마지막 상태 삭제 |
| `STATUS_HAS_ISSUES` | 409 | 이슈가 있는 상태를 `moveTo` 없이 삭제 |
| `ISSUE_TYPE_NAME_DUPLICATED` | 409 | 같은 이름의 유형 있음 |
| `LAST_ISSUE_TYPE_IN_LEVEL` | 409 | 계층의 마지막 유형 삭제 |
| `ISSUE_TYPE_HAS_ISSUES` | 409 | 이슈가 있는 유형을 `moveTo` 없이 삭제 |
| `ISSUE_TYPE_LEVEL_MISMATCH` | 400 | 다른 계층의 유형으로 변경 · 이동 |
| `INVALID_PARENT` | 400 | 부모 계층 규칙 위반, 다른 프로젝트의 이슈 |
| `EPIC_NOT_ALLOWED_IN_SPRINT` | 400 | 에픽을 스프린트에 넣음 |
| `SUBTASK_SPRINT_FOLLOWS_PARENT` | 400 | 하위 작업만 따로 스프린트 변경 |
| `SPRINT_DISABLED` | 409 | 스프린트 사용이 꺼진 프로젝트에서 스프린트 기능 사용 |
| `SPRINT_ACTIVE_CANNOT_DISABLE` | 409 | 진행 중 스프린트가 있는데 스프린트 사용 끄기 |
| `SPRINT_ALREADY_ACTIVE` | 409 | 진행 중 스프린트가 있는데 시작 |
| `SPRINT_NOT_FUTURE` | 409 | 계획 상태가 아닌 스프린트 시작 · 삭제 · 이동 대상 |
| `SPRINT_NOT_ACTIVE` | 409 | 진행 중이 아닌 스프린트 완료 |
| `SPRINT_CLOSED` | 409 | 종료된 스프린트에 이슈 넣기 · 빼기 |
| `INVALID_SPRINT_DATES` | 400 | 종료일이 시작일보다 빠름 |

- 새 기능을 만들 때 에러 코드는 백엔드 `ErrorCode`와 이 표에 함께 추가한다.
