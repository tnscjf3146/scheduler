# 유저플로우 (MVP)

[기능 명세](../spec/feature-spec.md)의 기능을 사용자가 어떤 순서로 쓰는지 정리한다. 세부 규칙은 [정책](../policy/policy.md)을 따른다. 괄호 안의 ID는 기능 명세의 기능 ID다.

- 다이어그램은 Mermaid로 그려 GitHub에서 바로 보인다.
- 모양: `([ ])` 시작·끝, `[ ]` 화면·행동, `{ }` 분기, `[[ ]]` 다른 플로우로 이동.

## 화면 구조

```mermaid
flowchart LR
    Login[로그인] --> Projects[프로젝트 목록]
    Signup[회원가입] --> Login
    Projects --> Dashboard[대시보드]

    subgraph 프로젝트
        Dashboard
        Backlog["백로그<br/>(스프린트 사용 시)"]
        Board[보드]
        Issues[이슈 목록 · 검색]
        Settings["프로젝트 설정<br/>(관리자)"]
    end

    Dashboard --- Backlog
    Dashboard --- Board
    Dashboard --- Issues
    Dashboard --- Settings

    Backlog --> Detail[이슈 상세]
    Board --> Detail
    Issues --> Detail
    Dashboard --> Detail

    Settings --> SetGeneral[일반 · 스프린트 사용]
    Settings --> SetMembers[멤버]
    Settings --> SetStatus[상태]
    Settings --> SetType[이슈 유형]

    Header[상단 공통] --> Noti[알림]
    Header --> MyInfo[내 정보 · 탈퇴]
    Header --> KeyJump[이슈 키로 바로 가기]
```

| 화면 | 들어가는 곳 | 기능 |
|---|---|---|
| 로그인 · 회원가입 | 첫 화면 | USER-1, 2 |
| 프로젝트 목록 | 로그인 후 첫 화면 | PRJ-1, 2 |
| 대시보드 | 프로젝트를 고르면 첫 화면 | DASH-1~8 |
| 백로그 | 프로젝트 메뉴. **스프린트 사용이 켜진 프로젝트만** | BACKLOG, SPRINT |
| 보드 | 프로젝트 메뉴 | BOARD-1~4 |
| 이슈 목록 · 검색 | 프로젝트 메뉴, 대시보드 위젯 클릭 | SEARCH-1~2 |
| 이슈 상세 | 어느 화면에서든 이슈를 누르면 | ISSUE, CMT |
| 프로젝트 설정 | 프로젝트 메뉴. **관리자만** | PRJ-3~7, WF |
| 알림 · 내 정보 · 키로 바로 가기 | 상단 공통 영역 | NOTI, USER-3~4, SEARCH-3 |

- 웹은 왼쪽 사이드바에 프로젝트 메뉴, 앱은 하단 탭에 대시보드 · 백로그 · 보드 · 이슈를 둔다.
- 이슈 상세는 웹은 오른쪽 패널(또는 모달), 앱은 새 화면으로 연다.

## 1. 시작하기

### 1-1. 회원가입 · 로그인 (USER-1, 2)

```mermaid
flowchart TD
    Start([앱 실행]) --> Logged{로그인 상태?}
    Logged -- 예 --> Projects[프로젝트 목록]
    Logged -- 아니오 --> Login[로그인 화면]

    Login --> HasAccount{계정 있음?}
    HasAccount -- 아니오 --> Signup[회원가입: 이메일, 비밀번호, 이름]
    Signup --> SignupCheck{입력 검증}
    SignupCheck -- 이메일 중복 · 형식 오류 --> Signup
    SignupCheck -- 통과 --> Login

    HasAccount -- 예 --> Input[이메일, 비밀번호 입력]
    Input --> Auth{일치?}
    Auth -- 아니오 --> Err[오류 표시] --> Input
    Auth -- 예 --> Projects
```

- 가입이 끝나면 로그인 화면으로 돌아가 이메일을 미리 채워 둔다.
- 로그인 실패 메시지는 "이메일 또는 비밀번호가 맞지 않습니다" 하나로 통일한다 (어느 쪽이 틀렸는지 알려주지 않는다).

### 1-2. 첫 프로젝트 만들기 (PRJ-1)

```mermaid
flowchart TD
    Projects[프로젝트 목록] --> Empty{프로젝트 있음?}
    Empty -- 아니오 --> Guide["빈 화면 안내<br/>'첫 프로젝트를 만들어 보세요'"] --> New
    Empty -- 예 --> List[목록에서 선택] --> Dashboard
    Projects --> New[새 프로젝트]

    New --> Form["이름 입력<br/>키 자동 제안 (이름에서) · 수정 가능<br/>설명 · 스프린트 사용 (기본 켬)"]
    Form --> KeyCheck{키 검증}
    KeyCheck -- 형식 오류 · 중복 --> Form
    KeyCheck -- 통과 --> Create["생성<br/>나 = 리드 · 관리자<br/>기본 상태 3개 · 유형 5개"]
    Create --> Dashboard[대시보드]
    Dashboard --> Next[[2. 멤버 추가]]
```

- 키는 이름을 입력하는 동안 자동으로 제안한다 (예: "Scheduler App" → `SA`). 사용자가 고칠 수 있다.
- 키 입력 칸 아래에 "키는 나중에 바꿀 수 없습니다"를 보여준다.

## 2. 멤버 관리 (PRJ-5~7)

```mermaid
flowchart TD
    Settings[프로젝트 설정 → 멤버] --> Action{무엇을?}

    Action -- 추가 --> Email[이메일 입력]
    Email --> Found{가입한 사용자?}
    Found -- 아니오 --> NotFound["'가입한 사용자만 추가할 수 있습니다'"] --> Email
    Found -- 이미 멤버 --> Already[이미 멤버라고 표시] --> Email
    Found -- 예 --> Role[역할 선택: 관리자 / 멤버] --> Added([추가됨])

    Action -- 역할 변경 · 내보내기 --> LastAdmin{마지막 관리자 또는 리드?}
    LastAdmin -- 예 --> Block[막고 이유 표시]
    LastAdmin -- 아니오 --> Confirm[확인 창] --> Done(["완료<br/>내보낸 사람의 담당 이슈 → 미배정"])
```

- 멤버(관리자 아님)에게는 설정 메뉴가 보이지 않는다. 대신 프로젝트 메뉴의 "나가기"만 있다 (리드·마지막 관리자는 막힘).

## 3. 이슈

### 3-1. 이슈 만들기 (ISSUE-1, BACKLOG-4)

```mermaid
flowchart TD
    Where{어디서 만드나?}
    Where -- 상단 '만들기' 버튼 --> Full
    Where -- 백로그 · 스프린트 영역 맨 아래 --> Quick["빠른 생성: 제목만 입력 후 Enter"]
    Where -- 보드 열 맨 아래 --> Quick
    Where -- 이슈 상세 '하위 작업 추가' --> Sub["하위 작업 빠른 생성<br/>유형 · 부모 자동"]

    Full["만들기 폼<br/>유형 · 제목 (필수)<br/>설명 · 담당자 · 우선순위 · 레이블 · 기한 · 부모 · 스프린트"] --> Valid{검증}
    Valid -- 제목 없음 · 부모 규칙 위반 --> Full
    Valid -- 통과 --> Created

    Quick --> Created["생성 · 키 발급 (SCH-13)<br/>목록 맨 아래에 추가"]
    Sub --> Created
    Created --> Toast["알림 메시지 'SCH-13 생성됨' · 누르면 상세로"]
    Created -. 담당자를 지정했으면 .-> Noti[[담당자에게 ASSIGNED 알림]]
```

- 빠른 생성의 유형은 그 프로젝트의 첫 번째 `STANDARD` 유형(기본: 스토리)이고, 들어가는 곳에 따라 기본값이 정해진다.

| 만든 곳 | 스프린트 | 상태 |
|---|---|---|
| 백로그 영역 | 없음 (백로그) | `TODO` 분류의 첫 상태 |
| 스프린트 영역 | 그 스프린트 | `TODO` 분류의 첫 상태 |
| 보드 열 | 진행 중 스프린트 (스프린트 사용 끈 프로젝트는 없음) | 그 열의 상태 |

- 만들기 폼에서 유형을 고르면 부모 칸이 바뀐다: 에픽 → 부모 칸 숨김, 하위 작업 → 부모 필수.

### 3-2. 이슈 보고 고치기 (ISSUE-2~4, 6)

```mermaid
flowchart TD
    Open[이슈 상세 열기] --> View["키 · 제목 · 유형 · 상태 · 담당자 · 우선순위<br/>레이블 · 기한 · 부모 · 스프린트 · 설명<br/>하위 이슈 목록 · 댓글"]
    View --> Edit{무엇을?}
    Edit -- 필드 클릭 --> Inline[그 자리에서 편집] --> Save[바로 저장]
    Edit -- 상태 선택 --> Status[상태 변경] --> Save
    Edit -- 레이블 입력 --> Label{있는 레이블?}
    Label -- 예 --> Attach[붙이기] --> Save
    Label -- 아니오 --> NewLabel["'새 레이블 만들기' 선택"] --> Attach
    Edit -- 댓글 --> Cmt[[5. 댓글 · 멘션]]
    Edit -- 삭제 --> Del[[3-4. 이슈 삭제]]

    Save -. 담당자 변경 .-> N1[[새 담당자에게 ASSIGNED]]
    Save -. 상태 변경 .-> N2[[보고자 · 담당자에게 STATUS_CHANGED]]
```

- 저장 버튼은 없다. 필드마다 바뀌는 즉시 저장한다. 실패하면 이전 값으로 되돌리고 오류를 보여준다.

### 3-3. 보드에서 진행하기 (BOARD-1~3)

```mermaid
flowchart TD
    Board[보드 열기] --> Mode{스프린트 사용?}
    Mode -- 켬 --> Active{진행 중 스프린트?}
    Active -- 없음 --> EmptyBoard["빈 보드 + '백로그에서 스프린트를 시작하세요'"] --> GoBacklog[[4. 스프린트]]
    Active -- 있음 --> ShowSprint[진행 중 스프린트의 이슈]
    Mode -- 끔 --> ShowAll["모든 이슈<br/>완료 열은 최근 14일"]

    ShowSprint --> Work
    ShowAll --> Work
    Work{무엇을?}
    Work -- 카드를 다른 열로 드래그 --> Move["상태 변경 + 놓은 자리로 순서 변경"]
    Work -- 같은 열 안에서 드래그 --> Reorder[순서만 변경]
    Work -- 필터 --> Filter["담당자 · 유형 · 우선순위 · 레이블 · 내 이슈만"] --> Work
    Work -- 카드 클릭 --> Detail[[3-2. 이슈 상세]]

    Move --> IsDone{완료 분류 열?}
    IsDone -- 예 --> Resolved[resolved_at 기록] --> Saved
    IsDone -- 아니오 --> Saved([저장])
    Reorder --> Saved
    Move -. 실패 .-> Rollback[카드를 원래 자리로 되돌리고 오류 표시]
```

- 드래그는 화면에 먼저 반영하고 서버에 저장한다 (낙관적 업데이트). 실패하면 되돌린다.
- 앱: 열은 가로로 스와이프해 넘긴다. 카드를 길게 눌러 드래그하고, 화면 가장자리로 끌면 옆 열로 넘어간다. 드래그가 불편하면 카드 메뉴의 "상태 변경"을 쓴다.

### 3-4. 이슈 삭제 (ISSUE-5)

```mermaid
flowchart TD
    Menu[이슈 상세 → 메뉴 → 삭제] --> Can{관리자 또는 보고자?}
    Can -- 아니오 --> Hidden[삭제 메뉴가 보이지 않음]
    Can -- 예 --> Confirm["확인 창<br/>'하위 작업 N개, 댓글이 함께 삭제됩니다. 복구할 수 없습니다'<br/>'끝난 이슈라면 완료 상태로 옮기세요'"]
    Confirm -- 취소 --> Back([상세로])
    Confirm -- 삭제 --> Delete["삭제<br/>하위 작업 · 댓글 · 알림 함께 삭제<br/>에픽이면 아래 이슈의 부모만 비움"] --> Leave([보던 목록으로 돌아감])
```

## 4. 스프린트 (BACKLOG, SPRINT)

스프린트 사용이 켜진 프로젝트에만 있다.

```mermaid
flowchart TD
    Backlog["백로그 화면<br/>진행 중 스프린트 → 계획된 스프린트 → 백로그"] --> Plan

    subgraph 계획
        Plan[스프린트 만들기] --> Fill["이슈를 스프린트로 드래그<br/>(여러 개 골라 한 번에)"]
        Fill --> Order[드래그로 순서 정하기]
    end

    Order --> CanStart{관리자이고, 진행 중 스프린트 없음?}
    CanStart -- 아니오 --> Wait[시작 버튼 비활성 · 이유 표시]
    CanStart -- 예 --> StartForm["시작: 기간 (기본 오늘 ~ 14일 뒤) · 목표"] --> Active[진행 중]

    Active --> Board[[3-3. 보드에서 진행]]
    Board --> Due{종료일 지남?}
    Due -- 예 --> Badge[보드에 '종료일 지남' 표시]
    Due -- 아니오 --> Board
    Badge --> Complete

    Active --> Complete["완료 (관리자)"]
    Complete --> Summary["완료 N개 · 남은 이슈 M개 표시"]
    Summary --> Left{남은 이슈 있음?}
    Left -- 아니오 --> Closed
    Left -- 예 --> Dest["보낼 곳 선택<br/>백로그 / 계획된 스프린트"] --> Closed(["종료<br/>완료 이슈는 그 스프린트 기록에 남음"])
    Closed --> Backlog
```

- 에픽은 스프린트로 드래그할 수 없다 (놓을 수 없음 표시). 하위 작업은 부모를 옮기면 따라간다.
- 계획된 스프린트 삭제: 스프린트 메뉴 → 삭제 → 확인 창 ("이슈 N개는 백로그로 돌아갑니다").

## 5. 댓글 · 멘션 (CMT-1, 2)

```mermaid
flowchart TD
    Detail[이슈 상세 → 댓글 입력] --> Type[내용 입력]
    Type --> At{'@' 입력?}
    At -- 예 --> Pick[프로젝트 멤버 목록에서 선택] --> Type
    At -- 아니오 --> Submit[등록]
    Submit --> Saved([댓글 표시])
    Saved -. 멘션된 사람 .-> N1[[MENTIONED]]
    Saved -. 보고자 · 담당자 .-> N2["COMMENTED<br/>(이미 멘션으로 받은 사람은 제외)"]

    Saved --> Mine{내 댓글?}
    Mine -- 예 --> EditDel[수정 · 삭제]
    Mine -- 아니오, 관리자 --> DelOnly[삭제만]
```

## 6. 알림 (NOTI-1~3)

```mermaid
flowchart TD
    Bell["상단 벨 아이콘<br/>안 읽은 수 표시"] --> List[알림 목록 · 최신순]
    List --> Pick{무엇을?}
    Pick -- 알림 클릭 --> Read[읽음 처리] --> Detail[해당 이슈 상세로 이동]
    Pick -- 모두 읽음 --> ReadAll[전부 읽음 · 숫자 사라짐]
```

| 알림 문구 예 | 종류 |
|---|---|
| 김철수님이 **SCH-12**를 회원님에게 배정했습니다 | `ASSIGNED` |
| 김철수님이 **SCH-12** 댓글에서 회원님을 언급했습니다 | `MENTIONED` |
| 김철수님이 **SCH-12**에 댓글을 남겼습니다 | `COMMENTED` |
| 김철수님이 **SCH-12**를 **진행 중**으로 변경했습니다 | `STATUS_CHANGED` |

## 7. 대시보드 (DASH-1~8)

```mermaid
flowchart TD
    Enter[프로젝트 선택] --> Dash[대시보드]
    Dash --> W{위젯 클릭}
    W -- 내 이슈 · 기한 지난 이슈의 항목 --> Detail[이슈 상세]
    W -- 숫자 · 막대 --> Search["이슈 목록<br/>그 조건으로 필터된 상태"]
    W -- 스프린트 진행률 --> Board[보드]
    W -- 에픽 진행률 --> Epic[에픽 상세]
```

- 예: "담당자별 이슈 수"에서 김철수 막대를 누르면 → 이슈 목록이 `담당자 = 김철수, 미완료` 필터로 열린다.

## 8. 프로젝트 설정 (관리자)

### 8-1. 상태 · 이슈 유형 관리 (WF-1~5)

```mermaid
flowchart TD
    Settings[설정 → 상태 또는 이슈 유형] --> Act{무엇을?}
    Act -- 추가 --> Add["이름 + 분류(상태) / 계층(유형) 선택"] --> Done([목록에 추가])
    Act -- 이름 변경 --> Rename[그 자리에서 수정] --> Done
    Act -- 순서 변경 --> Drag[드래그] --> Done
    Act -- 삭제 --> Last{그 분류 · 계층의 마지막 하나?}
    Last -- 예 --> Block[삭제 막고 이유 표시]
    Last -- 아니오 --> HasIssue{이 상태 · 유형의 이슈 있음?}
    HasIssue -- 없음 --> Confirm[확인 창] --> Deleted([삭제])
    HasIssue -- N개 --> Move["이슈를 옮길 대상 선택<br/>(유형은 같은 계층만)"] --> Deleted
```

- 분류·계층은 만든 뒤 바꿀 수 없어서, 수정 화면에서는 읽기 전용으로 보여준다.

### 8-2. 스프린트 사용 바꾸기

```mermaid
flowchart TD
    Toggle[설정 → 일반 → 스프린트 사용] --> On{지금 켜져 있음?}
    On -- 예, 끄려 함 --> Active{진행 중 스프린트?}
    Active -- 있음 --> Block["'진행 중 스프린트를 먼저 완료하세요'"]
    Active -- 없음 --> Off["끔<br/>백로그 메뉴 숨김 · 보드에 모든 이슈"]
    On -- 아니오, 켜려 함 --> TurnOn["켬<br/>백로그 메뉴 표시 · 모든 이슈는 백로그에서 시작"]
```

### 8-3. 프로젝트 삭제 (PRJ-4)

```mermaid
flowchart TD
    Danger[설정 → 일반 → 프로젝트 삭제] --> Confirm["확인 창<br/>'이슈 N개, 스프린트, 댓글이 모두 삭제됩니다. 복구할 수 없습니다'"]
    Confirm --> Type[프로젝트 키 입력]
    Type --> Match{키 일치?}
    Match -- 아니오 --> Disabled[삭제 버튼 비활성]
    Match -- 예 --> Delete[삭제] --> Projects([프로젝트 목록으로])
```

## 9. 탈퇴 (USER-4)

```mermaid
flowchart TD
    MyInfo[내 정보 → 탈퇴] --> Check{리드이거나 마지막 관리자인 프로젝트?}
    Check -- 있음 --> List["해당 프로젝트 목록 표시<br/>'리드를 넘기거나 프로젝트를 삭제하세요'"] --> Go[프로젝트 설정으로 이동 링크]
    Check -- 없음 --> Confirm["확인 창 + 비밀번호 입력<br/>'계정이 즉시 삭제됩니다. 작성한 이슈·댓글은 남습니다'"]
    Confirm --> Pw{비밀번호 일치?}
    Pw -- 아니오 --> Confirm
    Pw -- 예 --> Delete["삭제<br/>담당 이슈 → 미배정 · 작성자 → '알 수 없는 사용자'"] --> Out([로그아웃 · 로그인 화면])
```
