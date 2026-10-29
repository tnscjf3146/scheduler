# 앱 컨벤션

Kotlin + **Compose Multiplatform** 기준. Android를 먼저 만들고, iOS는 같은 코드에 나중에 붙인다. 빌드는 Gradle(Kotlin DSL, `libs.versions.toml`로 버전 관리)을 쓴다. 들여쓰기, 줄바꿈 같은 서식은 ktlint(`./gradlew ktlintFormat`)에, 코드 규칙 검사는 detekt(`./gradlew detekt`)에 맡기고 이 문서에는 적지 않는다.

## 라이브러리

| 용도 | 라이브러리 |
|---|---|
| UI | Compose Multiplatform, Material 3 |
| 화면 이동 | Navigation Compose (멀티플랫폼) |
| 상태 관리 | ViewModel (멀티플랫폼) + `StateFlow` |
| 서버 통신 | Ktor Client + kotlinx.serialization |
| 비동기 | Coroutines + Flow |
| 의존성 주입 | Koin |
| 로컬 저장 | Room (KMP), 설정값은 DataStore |

- 새 라이브러리는 **멀티플랫폼을 지원하는지** 먼저 확인한다. Android 전용 라이브러리(Retrofit, Hilt 등)는 `commonMain`에서 쓰지 않는다.

## 스타일

- 색·간격·모서리·글자 스타일은 **`MaterialTheme`과 디자인 토큰만** 쓴다 (`MaterialTheme.colorScheme.primary`, `AppSpacing.md`, `MaterialTheme.typography.titleMedium`).
- 하드코딩 값(`Color(0xFFFFFFFF)`, `13.dp`)은 쓰지 않는다. 필요한 값이 없으면 Figma와 `ui/theme/` 토큰에 먼저 추가한다.
- 문자열·이미지는 Compose Resources(`composeResources/`)에 두고 `Res.string.*`, `Res.drawable.*`로 불러온다.

## 디렉토리 구조

플랫폼 공통 코드는 `commonMain`에 두고, 플랫폼별 코드만 `androidMain`·`iosMain`에 둔다. 공통 코드 안에서는 기능(도메인) 단위로 나눈다.

```
composeApp/src/
├── commonMain/kotlin/com/scheduler/
│   ├── App.kt                   # 앱 진입점 (테마, 내비게이션)
│   ├── di/                      # Koin 모듈
│   ├── navigation/              # 라우트, NavHost
│   ├── core/
│   │   ├── network/             # Ktor 클라이언트 설정
│   │   ├── database/            # Room 설정
│   │   └── util/                # 유틸 함수 (*Util.kt)
│   ├── ui/
│   │   ├── theme/               # 색, 글꼴, 간격 토큰
│   │   └── component/           # 공통 컴포넌트 (AppButton, AppTextField …)
│   └── feature/{도메인}/          # 예: feature/issue, feature/project, feature/board
│       ├── data/                # API, Repository, DTO
│       ├── model/               # 화면에서 쓰는 모델
│       └── ui/                  # Screen, ViewModel, 기능 전용 컴포넌트
├── commonMain/composeResources/ # 문자열, 이미지
├── commonTest/kotlin/           # 공통 테스트
├── androidMain/kotlin/          # Android 전용 (MainActivity, expect 구현)
└── iosMain/kotlin/              # iOS 전용 (나중에)
```

- 플랫폼마다 구현이 다른 기능은 `commonMain`에 `expect`를 선언하고 `androidMain`·`iosMain`에 `actual`로 구현한다.

## 네이밍

- **패키지**: 소문자, 단어를 붙여 쓴다 (`_`, `-` 없음). 예: `com.scheduler.feature.issue`
- **파일·클래스**: `PascalCase`. 파일 하나에 대표 클래스 하나를 두고 파일명을 같게 한다.
- **Composable 함수**: `PascalCase` 명사. 다른 기능과 겹치지 않도록 도메인 이름을 앞에 붙인다. 예: 이슈 상세의 댓글 목록은 `IssueCommentList`
- **그 외 함수·변수**: `camelCase`. 상수(`const val`)는 `UPPER_SNAKE_CASE`.
- 클래스는 역할 접미사를 붙인다.

| 종류 | 접미사 | 예 |
|---|---|---|
| 화면 | `*Screen` | `IssueDetailScreen` |
| ViewModel | `*ViewModel` | `IssueDetailViewModel` |
| 화면 상태 | `*UiState` | `IssueDetailUiState` |
| Repository | `*Repository` | `IssueRepository` |
| API | `*Api` | `IssueApi` |
| DTO | `*Dto` (요청은 `*Request`, 응답은 `*Response`) | `IssueResponse` |
| Room 엔티티 / DAO | `*Entity` / `*Dao` | `IssueEntity` |
| Koin 모듈 | `*Module` | `issueModule` |
| 유틸 | `*Util` | `DateUtil` |
| 테스트 | `*Test` | `IssueDetailViewModelTest` |

## 상태 관리

- 화면 상태는 ViewModel이 `StateFlow<{화면}UiState>` 하나로 내보내고, 화면은 `collectAsStateWithLifecycle()`로 받는다.
- **상태 끌어올리기(state hoisting)**: `*Screen`만 ViewModel을 알고, 그 아래 Composable은 상태 값과 이벤트 콜백만 받는다. 그래야 Preview와 테스트가 쉽다.
- 서버 호출은 Repository를 거친다. ViewModel에서 `HttpClient`를 직접 쓰지 않는다.

```kotlin
@Composable
fun IssueDetailScreen(viewModel: IssueDetailViewModel = koinViewModel()) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    IssueDetailContent(
        uiState = uiState,
        onStatusChange = viewModel::changeStatus,
    )
}
```

## 테스트

- 로직(ViewModel, Repository, 유틸)은 테스트를 둔다. 공통 테스트는 `commonTest`에 `kotlin.test`로 작성한다.
- 실행: `./gradlew check` (ktlint, detekt, 테스트를 한 번에 돌린다). PR을 올리기 전에 통과시킨다.

## API 함수명

- 조회(GET)는 `get`으로 시작한다. 예: `getIssues`
- 변경(POST, PUT, PATCH, DELETE)은 `mutate`로 시작한다. 예: `mutateIssueStatus`

## 이벤트 콜백

- Composable 파라미터로 받는 콜백은 `on + 대상 + 동작`. 예: `onIssueCardClick`, `onStatusChange`
- ViewModel에서 이벤트를 처리하는 함수는 동사로 시작한다. 예: `changeStatus`, `deleteComment`

## 함수 선언

- Composable은 `Modifier`를 받는다면 **필수 파라미터 다음, 첫 번째 선택 파라미터**로 두고 기본값은 `Modifier`로 한다.
- 화면 단위 Composable에는 `@Preview`를 만든다. Preview 함수는 `private`, 이름은 `{Composable명}Preview`.
- 콜백은 람다를 쓰고, 넘길 함수가 이미 있으면 함수 참조(`viewModel::changeStatus`)를 쓴다.
