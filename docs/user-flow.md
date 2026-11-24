# User Flow

[기획서](plan.md)의 기능을 사용자가 어떤 순서로 쓰는지 정리한다. 나와 에이전트(터미널 세션)가 함께 일하는 exe 앱이다.

- 다이어그램은 Mermaid로 그려 GitHub에서 바로 보인다.
- 모양: `([ ])` 시작·끝, `[ ]` 화면·행동, `{ }` 분기.

## 화면 구조

exe를 실행하면 바로 대시보드가 열린다. 대시보드에는 섹션 4개가 있다.

```mermaid
flowchart LR
    Run([exe 실행]) --> Dashboard[대시보드]

    subgraph S1[1섹션]
        Upcoming[다가오는 일정]
        Agents[Agent]
    end

    subgraph S2[2섹션]
        Todo[할 일]
        Calendar[일정 달력]
    end

    subgraph S3[3섹션]
        Mail[메일 검토]
        Approval[결재 대기]
    end

    subgraph S4[4섹션 · 사이드 패널]
        Chat[챗봇]
    end

    Dashboard --- S1
    Dashboard --- S2
    Dashboard --- S3
    Dashboard --- S4
```

## 플로우

### 1섹션: 다가오는 일정

- 보기 전용이다. 이 위젯에서는 일정을 추가·수정할 수 없다.
- 2섹션에서 추가한 할 일 중 다가오는 것을 가까운 순서로 보여 준다.

```mermaid
flowchart TD
    Dashboard[대시보드] --> Upcoming[다가오는 일정 위젯]
    Add2[2섹션에서 할 일 추가] -.-> Upcoming
    Upcoming --> HasItem{다가오는 항목이 있는가?}
    HasItem -- 예 --> List[가까운 순서로 목록 표시]
    HasItem -- 아니오 --> Empty[다가오는 일정이 없다는 안내]
```

### 1섹션: Agent

- AI 팀원은 **역할별 에이전트 여러 개**다. 에이전트마다 맡은 역할이 다르다.
- **에이전트 하나 = 터미널 세션 하나.** 에이전트마다 자기 터미널 세션을 따로 가진다. 한 에이전트가 실행한 명령, 작업 폴더, 대화 기록은 다른 에이전트와 섞이지 않는다.
- 에이전트를 누르면 4섹션(사이드 패널)이 바로 그 에이전트의 터미널로 바뀐다. 지금 4섹션에 열린 에이전트는 목록에서 진하게 표시한다.
- 행 오른쪽 `⋯` 메뉴에 재시작·종료·설정 같은 동작을 둔다. (항목은 초안)
- 에이전트는 공식 CLI 에이전트(Claude Code, Codex 등)다. 로그인은 CLI가 처음 실행될 때 직접 한다.
- 에이전트를 누가 만들고 어떻게 관리하는지는 미정이다.

```mermaid
flowchart TD
    Widget[Agent 위젯] --> List[역할별 에이전트 목록]
    List --> Item[에이전트: 이름 · 역할]
    Item -- 누르기 --> Panel[4섹션이 그 에이전트의 터미널로 바뀜]
    Item --> Mark[목록에서 선택 표시]
    Item -- ⋯ 누르기 --> Menu[재시작 · 종료 · 설정]
```

### 2섹션: 할 일 · 일정(달력)

- 할 일 위젯에서 할 일을 추가한다.
- 추가한 할 일은 일정(달력) 위젯의 해당 날짜에 보인다. 1섹션 다가오는 일정에도 나온다.
- 할 일 입력 항목은 초안이다: 제목, 날짜·시각.

```mermaid
flowchart TD
    Todo[할 일 위젯] --> Add[할 일 추가]
    Add --> Input[제목 · 날짜·시각 입력]
    Input --> Valid{입력이 올바른가?}
    Valid -- 아니오 --> Error[오류 메시지] --> Input
    Valid -- 예 --> Saved[저장]
    Saved --> List[할 일 목록에 표시]
    Saved --> Calendar["일정(달력) 위젯의 해당 날짜에 표시"]
    Saved --> Upcoming[1섹션 다가오는 일정에 표시]
```

### 3섹션: 메일 검토

- Gmail, 네이버, 회사 메일 등 어떤 메일이든 연결할 수 있게 한다.
- exe가 메일 서버와 IMAP IDLE 연결을 열어 두고, 새 메일이 오면 바로 감지한다(IDLE을 지원하지 않으면 1분마다 확인). 개인 컴퓨터는 밖에서 접속할 수 없어서, 메일 서비스가 알림을 보내 주는 방식은 쓰지 않는다.
- AI가 메일을 읽고 요약한다. 도구를 모두 끈 Claude Code(`claude -p`)를 빈 폴더에서 실행한다. 목록에는 메일 원래 제목 대신 **요약을 제목으로** 보여 준다.
- 메일을 누르면 **요약 · 원문 · 답장 초안**을 보여 준다.
- 답장은 **사용자가 전송 버튼을 눌러야만** 보내진다. AI는 초안만 쓰고, 스스로 메일을 보내지 않는다.
- 사용자는 초안을 고친 뒤 보낼 수 있다. (초안)
- 메일을 읽는 AI는 터미널을 쓰지 않는다. 메일 본문에 숨은 지시가 명령 실행으로 이어지지 않게 하기 위해서다.

새 메일이 들어올 때 (앱 내부):

```mermaid
flowchart TD
    Mail([새 메일 도착]) --> Detect[exe가 새 메일 감지]
    Detect --> Save[메일 원문 저장]
    Save --> AI[AI가 메일 확인]
    AI --> Summary[요약 · 요약 제목 · 답장 초안 생성]
    Summary --> Ready[메일 검토 목록에 추가]
    AI -- 실패 --> Fail["원문 제목으로 목록에 추가<br/>요약 실패 표시"]
```

사용자:

```mermaid
flowchart TD
    Widget[메일 검토 위젯] --> HasMail{검토할 메일이 있는가?}
    HasMail -- 아니오 --> Empty[검토할 메일이 없다는 안내]
    HasMail -- 예 --> List[요약 제목 목록]
    List -- 메일 누르기 --> Detail[메일 상세]
    Detail --> S[요약]
    Detail --> O[원문]
    Detail --> D[답장 초안]
    D --> Edit[초안 수정]
    Edit --> SendBtn{사용자가 전송 버튼을 눌렀는가?}
    D --> SendBtn
    SendBtn -- 아니오 --> Keep[보내지 않음 · 초안 유지]
    SendBtn -- 예 --> Send[메일 전송]
    Send --> Result{전송 성공?}
    Result -- 예 --> Done[보낸 메일로 표시]
    Result -- 아니오 --> SendError[오류 메시지 · 초안 유지] --> Edit
```

### 3섹션: 결재 대기

- 에이전트가 내가 정해야 하는 사항을 **결재 문서**로 작성해 올린다. 예: 제출물 확정, 클라이언트에게 보낼 내용.
- 명령 실행 승인은 결재가 아니다. CLI 안에서 처리한다.
- 결재 문서 항목은 초안이다: 제목, 올린 에이전트, 올린 시각, 배경, 결정할 사항, 첨부.
- 나는 **승인** 또는 **반려**한다. 반려할 때는 사유를 적는다.
- 결과는 문서를 올린 에이전트에게 전달되고, 에이전트는 결과에 따라 작업을 이어 간다.

에이전트가 결재를 올릴 때:

```mermaid
flowchart TD
    Work([에이전트가 터미널 세션에서 작업 중]) --> Need{내가 정해야 하는 사항이 생겼는가?}
    Need -- 아니오 --> Work
    Need -- 예 --> Doc[결재 문서 작성]
    Doc --> Submit[결재 올리기]
    Submit --> Queue[결재 대기 목록에 추가]
    Submit --> Wait[에이전트는 결과를 기다림]
```

내가 결재할 때:

```mermaid
flowchart TD
    Widget[결재 대기 위젯] --> HasDoc{대기 중인 결재가 있는가?}
    HasDoc -- 아니오 --> Empty[대기 중인 결재가 없다는 안내]
    HasDoc -- 예 --> List[결재 문서 목록]
    List -- 문서 누르기 --> Detail[결재 문서 보기]
    Detail --> Decide{결정}
    Decide -- 승인 --> Approved[승인 처리]
    Decide -- 반려 --> Reason[반려 사유 입력] --> Rejected[반려 처리]
    Decide -- 닫기 --> List
    Approved --> Notify[결과를 올린 에이전트에게 전달]
    Rejected --> Notify
    Notify --> Continue[에이전트가 결과에 따라 작업 계속]
```

### 4섹션: 챗봇 (사이드 패널)

- 4섹션은 1섹션에서 고른 **에이전트의 터미널 세션**을 보여 주는 창이다. 터미널 화면을 그대로 보여 주고, 사용자는 그 터미널에 직접 입력한다.
- 입력하면 그 에이전트가 자기 터미널 세션에서 작업하고 결과를 터미널에 출력한다.
- 다른 에이전트로 바꾸면 그 에이전트의 세션으로 넘어간다. 돌아오면 이전 대화와 작업 상태가 그대로 남아 있다.
- 아직 고른 에이전트가 없을 때 무엇을 보여 줄지는 미정이다.

```mermaid
flowchart TD
    Pick[1섹션 Agent에서 에이전트 누르기] --> Panel[4섹션이 그 에이전트의 터미널 세션으로 바뀜]
    Panel --> Send[터미널에 입력]
    Send --> Work[에이전트가 자기 터미널 세션에서 작업]
    Work --> Reply[터미널에 결과 출력] --> Send
    Panel -- 다른 에이전트 선택 --> Other[그 에이전트의 세션으로 전환<br/>이전 세션은 그대로 유지]
```
