# Git 컨벤션

## 브랜치 전략

```
main      ●───────────────●───────●──────────▶  배포된 코드 (v1.0.0, v1.0.1 ...)
           \             / \     /
hotfix      \           /   ●───●                hotfix/* : 배포 후 긴급 수정
             \         /         \
develop       ●───●───●───────────●───▶          다음 배포를 모으는 곳
               \   / \   /
feature         ●─●   ●─●                        {FE|BE}/feature/* : 기능 하나 개발
```

| 브랜치 | 역할 | 만드는 곳 | 합치는 곳 |
|---|---|---|---|
| `main` | 실제 배포된 코드. 항상 배포 가능한 상태 | - | - |
| `develop` | 다음 배포에 들어갈 기능을 모으는 곳 | `main` (최초 1회) | `main` (배포할 때) |
| `{FE\|BE}/feature/*`, `{FE\|BE}/fix/*` | 기능 하나 개발, 버그 수정 | `develop` | `develop` |
| `hotfix/*` | 배포된 버전의 긴급 버그 수정 | `main` | `main` **그리고** `develop` |

### 규칙
- `main`, `develop`에는 **직접 커밋·푸시하지 않는다.** 항상 PR로 합친다.
- 기능 개발은 `develop`에서 `{FE|BE}/feature/*`를 만들어 작업하고, 끝나면 `develop`으로 PR을 올린다.
- 배포할 때 `develop` → `main` PR을 올리고, 합친 뒤 `main`에 버전 태그를 붙인다.
- 배포 후 급한 버그는 `main`에서 `hotfix/*`를 만들어 고치고, `main`과 `develop` 양쪽에 합친다. 평소 버그는 hotfix가 아니라 `{FE|BE}/fix/*`로 `develop`에서 고친다.
- 합친 `{FE|BE}/feature/*`, `{FE|BE}/fix/*`, `hotfix/*` 브랜치는 지운다.

## 브랜치 이름

앞에 영역(`FE`, `BE`)을 붙이고, 나머지는 영문 소문자 `kebab-case`. 이슈 번호는 붙이지 않는다.

```
FE/feature/{기능}             FE/feature/issue-board
BE/feature/{기능}             BE/feature/issue-create
FE/fix/{내용}                 FE/fix/board-drag-drop
BE/fix/{내용}                 BE/fix/issue-status-validation
docs/{내용}                   docs/convention             (문서·정리 작업)
hotfix/{버전}-{내용}          hotfix/1.0.1-login-error
```

- PR 제목은 커밋 메시지 규칙을 따른다.

## 합치는 방식 (PR)

| PR | 합치는 방식 | 이유 |
|---|---|---|
| `{FE\|BE}/feature/*`, `{FE\|BE}/fix/*` → `develop` | **Squash and merge** | 기능 하나가 `develop`에 커밋 하나로 남아 이력이 깔끔하다 |
| `develop` → `main` | **Create a merge commit** | 배포 단위를 그대로 남긴다 |
| `hotfix/*` → `main`, `develop` | **Create a merge commit** | 두 브랜치에 같은 수정이 들어간 것을 추적하기 쉽다 |

- Squash로 합칠 때 PR 제목이 커밋 메시지가 되므로, **PR 제목도 아래 커밋 메시지 규칙을 따른다.**
- PR 본문에는 무엇을 왜 바꿨는지, 관련 이슈(`Closes #12`), 화면 변경이 있으면 스크린샷을 적는다.

## 버전과 태그

`main`에 합칠 때마다 `v주.부.수` 태그를 붙인다 ([Semantic Versioning](https://semver.org/lang/ko/)).

| 올리는 자리 | 언제 | 예 |
|---|---|---|
| 주(Major) | 호환되지 않는 큰 변경 | v1.0.0 → v2.0.0 |
| 부(Minor) | 기능 추가 (`develop` → `main` 배포) | v1.0.0 → v1.1.0 |
| 수(Patch) | 버그 수정 (hotfix) | v1.1.0 → v1.1.1 |

기획 스냅샷 태그(예: `plan-v1-login`)는 `plan-` 접두어를 붙여 버전 태그와 구분한다.

## 커밋 메시지

[Conventional Commits](https://www.conventionalcommits.org/ko/v1.0.0/) 형식을 따른다.

```
<타입>(<범위>): <제목>

<본문>

<꼬리말>
```

### 타입

| 타입 | 언제 |
|---|---|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `refactor` | 동작은 그대로 두고 코드 구조 개선 |
| `style` | 코드 포맷, 세미콜론 등 동작과 무관한 변경 (UI 스타일 변경은 `design`) |
| `design` | 화면 디자인, CSS 변경 |
| `docs` | 문서 (기획, README, 주석 등) |
| `test` | 테스트 추가·수정 |
| `chore` | 빌드 설정, 패키지, 기타 잡일 |
| `ci` | CI/CD 설정 |
| `perf` | 성능 개선 |

### 범위 (선택)

어느 쪽을 바꿨는지 적는다: `be`(백엔드), `fe`(프론트엔드), `admin`, `db`, `infra`, `docs`.

### 제목
- **한국어로 쓴다.** 영어 고유명사·코드 이름은 그대로 쓴다.
- 50자 이내, 끝에 마침표를 찍지 않는다.
- "~한다"가 아니라 **"~추가", "~수정"처럼 짧게** 끝낸다.
- 무엇을 했는지가 드러나게 쓴다. "수정", "버그 고침"처럼 내용 없는 제목은 쓰지 않는다.

### 본문 (선택)
- 제목과 한 줄 띄우고 쓴다.
- **무엇을 왜** 바꿨는지 적는다. 어떻게는 코드에 있다.
- 한 줄 72자 안팎에서 줄바꿈한다.

### 꼬리말 (선택)
- 이슈: `Closes #12`, `Refs #20`
- 하위 호환이 깨지는 변경: `BREAKING CHANGE: 설명`

### 예시

```
feat(be): 이슈 생성 API 추가

이슈 키는 프로젝트 키 + 순번(예: SCH-12)으로 자동 발급하고
같은 프로젝트 안에서 중복되지 않게 한다.

Closes #12
```

```
fix(fe): 보드에서 이슈를 드래그하면 상태가 바뀌지 않는 문제 수정
```

```
feat(be): 이슈 상태 전환 워크플로 추가
docs: 이슈 트래커 정책 문서 추가
design(fe): 칸반 보드 카드 레이아웃 변경
refactor(be): 이슈 저장 로직을 서비스 계층으로 분리
chore: ESLint, Prettier 설정 추가
```

### 하지 말 것
- 여러 기능을 커밋 하나에 섞지 않는다. 커밋 하나는 변경 하나.
- `WIP`, `asdf`, `수정`, `final` 같은 메시지를 `develop`·`main`에 남기지 않는다 (feature 브랜치 안에서는 괜찮다. Squash할 때 PR 제목으로 정리된다).
