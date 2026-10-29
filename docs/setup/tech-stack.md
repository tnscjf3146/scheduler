# 기술 스택

웹, 백엔드, 앱에서 쓰는 언어·프레임워크와 각각의 특징. 세팅 방법은 영역별 문서를 본다.

| 영역 | 스택 | 세팅 |
|---|---|---|
| 웹 (프론트엔드) | React + TypeScript, Vite, Node.js | [frontend-setup.md](frontend-setup.md) |
| 백엔드 | Java + Spring Boot, MySQL | [backend-setup.md](backend-setup.md) |
| 앱 | Kotlin + Compose Multiplatform (Android 먼저) | [app-setup.md](app-setup.md) |

## 저장소 구조

한 저장소에 세 영역을 폴더로 나눠 둔다 (모노레포).

```
scheduler/
├── frontend/        # React 웹
├── backend/         # Spring Boot API 서버
├── app/             # Compose Multiplatform 앱
├── docs/            # 기획 · 설계 · 컨벤션
└── docker-compose.yml   # 로컬 MySQL
```

```
 [웹 브라우저]      [Android 앱]
  React (frontend)   Compose (app)
        │                 │
        └──── HTTP/JSON ──┘
                 │
        Spring Boot (backend)  ── REST API
                 │
              MySQL
```

- 웹과 앱은 같은 REST API를 쓴다. 화면 로직은 각자, 데이터 규칙은 서버 한 곳에서 지킨다.

## 버전

2026-10 작성 기준. 세팅할 때 공식 사이트에서 최신 안정 버전을 한 번 더 확인한다.

| 항목 | 버전 | 비고 |
|---|---|---|
| Node.js | 24 LTS | 26이 2026-10-28에 LTS가 될 예정이었다. 팀 전체가 같은 메이저를 쓴다 |
| pnpm | 최신 | Corepack으로 설치 |
| React | 19 | |
| Vite | 8 | |
| TypeScript | 최신 5.x 이상 | |
| Java (JDK) | 25 LTS | Spring Boot 4는 Java 17 이상 필요 |
| Spring Boot | 4.x 최신 | Spring Framework 7 기반 |
| MySQL | 8.4 LTS | |
| Kotlin | 최신 2.x | Compose Multiplatform은 최신 Kotlin과 호환 |
| Compose Multiplatform | 최신 1.x | |
| Android Studio | 최신 안정 버전 | |

---

## 웹: React + TypeScript

### React
UI를 **컴포넌트** 단위로 만드는 라이브러리. Meta가 만들었고 웹 프론트엔드에서 가장 많이 쓴다.

- **선언형 UI**: "상태가 이러면 화면은 이렇다"만 적으면, 상태가 바뀔 때 React가 화면을 알아서 다시 그린다. DOM을 직접 고치지 않는다.
- **컴포넌트**: 화면을 `IssueCard`, `BoardColumn` 같은 함수 단위로 쪼개 조립한다. 같은 컴포넌트를 여러 곳에서 다시 쓴다.
- **훅(Hook)**: `useState`(상태), `useEffect`(부수 효과), `useMemo` 같은 함수로 컴포넌트에 기능을 붙인다. 공통 로직은 커스텀 훅(`useAuth`)으로 뺀다.
- **단방향 데이터 흐름**: 데이터는 부모 → 자식으로 props를 타고 내려가고, 자식은 콜백(`onIssueClick`)으로 부모에게 알린다. 흐름이 한 방향이라 추적하기 쉽다.
- **라이브러리일 뿐이다**: 라우팅, 서버 통신, 전역 상태는 React가 정하지 않는다. 필요한 라이브러리를 골라 붙인다 (아래 표).
- **생태계**: 드래그 앤 드롭, 차트, 폼 등 거의 모든 기능에 검증된 라이브러리가 있다.

### TypeScript
JavaScript에 **타입**을 더한 언어. 빌드할 때 JavaScript로 바뀌어 브라우저에서 돈다.

- 변수·함수·API 응답의 모양을 타입으로 적어, 실행 전에 오타·잘못된 필드 접근을 잡는다. 예: `issue.titel` → 컴파일 오류.
- 에디터 자동완성·이름 바꾸기가 정확해져 큰 코드도 안전하게 고친다.
- 백엔드 DTO와 같은 모양의 타입(`IssueResponse`)을 두면 API가 바뀔 때 고칠 곳이 바로 드러난다.

### Vite
개발 서버 + 빌드 도구.

- 개발 서버가 거의 즉시 뜨고, 코드를 저장하면 바뀐 모듈만 브라우저에 바로 반영한다 (HMR).
- `pnpm build`로 배포용 정적 파일(`dist/`)을 만든다. Vite 8부터 번들러가 Rolldown으로 바뀌어 빌드가 빠르다.
- 설정이 적다. React, TypeScript, Tailwind는 플러그인 한 줄씩이면 된다.

### Node.js · pnpm
- **Node.js**: 브라우저 밖에서 JavaScript를 실행하는 런타임. 웹 프로젝트에서는 **개발 도구(Vite, 테스트, 린트)를 돌리는 데만** 쓴다. 서버는 Spring Boot라 Node로 서버를 만들지 않는다. Node 24부터 `.ts` 파일을 바로 실행할 수 있어 테스트를 별도 변환 없이 돌린다.
- **pnpm**: 패키지 매니저. 패키지를 디스크에 한 번만 저장하고 링크해서 설치가 빠르고 용량이 적다. 선언하지 않은 패키지는 import할 수 없어 의존성 실수를 막는다.

### 함께 쓰는 라이브러리

| 용도 | 라이브러리 | 특징 |
|---|---|---|
| 스타일 | Tailwind CSS v4 | 클래스 이름으로 스타일을 바로 적는다. 디자인 토큰을 CSS 변수로 정의 |
| 라우팅 | React Router | URL ↔ 페이지 연결 (`/projects/SCH/board`) |
| 서버 상태 | TanStack Query | API 응답 캐시, 로딩·오류 상태, 재요청, 낙관적 업데이트(보드 드래그) |
| 전역 상태 | Redux Toolkit | 로그인 사용자 등 화면 전체가 쓰는 상태 (`*.slice.ts`) |
| 드래그 앤 드롭 | dnd-kit | 보드 카드 · 백로그 순서. 키보드 · 터치 지원 |
| 차트 | Recharts | 대시보드 위젯 |
| 서식 · 검사 | Prettier, oxlint | 서식 자동 정리, 빠른 린트 |

- 서버 통신은 브라우저 내장 `fetch`를 감싼 함수 하나(`lib/apis/client.ts`)로 한다. 별도 HTTP 라이브러리는 쓰지 않는다.

---

## 백엔드: Java + Spring Boot

### Java
정적 타입 객체지향 언어. JVM 위에서 돌아 운영체제와 상관없이 같은 코드가 돈다.

- **안정성**: 오래 쓰여 대규모 서비스에서 검증됐고, 하위 호환을 강하게 지킨다.
- **LTS**: 2년마다 장기 지원 버전(17, 21, 25 …)이 나온다. 운영 서버는 LTS를 쓴다.
- **최신 문법**: `record`(불변 DTO 한 줄 선언), `switch` 패턴 매칭, 텍스트 블록, **가상 스레드**(요청마다 가벼운 스레드를 써서 적은 자원으로 많은 동시 요청 처리).

### Spring Boot
Spring Framework로 서버를 빠르게 만들게 해주는 도구. 한국 백엔드에서 가장 많이 쓴다.

- **의존성 주입(DI)**: 객체를 직접 `new` 하지 않고 스프링이 만들어 넣어준다. `IssueService`는 `IssueRepository`를 생성자로 받기만 하면 된다. 테스트 때 가짜 객체로 바꾸기 쉽다.
- **자동 설정**: 의존성을 추가하면 기본 설정이 자동으로 된다. 예: MySQL 드라이버 + JPA를 넣고 접속 정보만 적으면 DB 연결이 끝난다.
- **스타터(Starter)**: `spring-boot-starter-web`처럼 기능별 묶음으로 의존성을 추가한다. 버전 궁합은 스프링이 맞춰준다.
- **내장 서버**: Tomcat이 들어 있어 `java -jar app.jar` 하나로 서버가 뜬다.
- **계층 구조**: Controller(요청·응답) → Service(비즈니스 규칙, 트랜잭션) → Repository(DB). 이 프로젝트는 [백엔드 컨벤션](../convention/backend-convention.md)대로 기능(도메인) 패키지 안에 함께 둔다.
- **트랜잭션**: `@Transactional` 하나로 메서드를 하나의 DB 트랜잭션으로 묶는다. 이슈 번호 발급(`SELECT … FOR UPDATE`)처럼 동시성이 중요한 곳에 쓴다.
- **Spring Boot 4**: Spring Framework 7 기반, Java 17 이상. null 안전성 어노테이션(JSpecify), API 버전 관리 기능이 들어갔다.

### 함께 쓰는 라이브러리

| 용도 | 라이브러리 | 특징 |
|---|---|---|
| 웹 API | Spring Web (Spring MVC) | `@RestController`로 REST API |
| DB 접근 | Spring Data JPA (Hibernate) | 엔티티 클래스 ↔ 테이블 매핑. 기본 CRUD는 인터페이스 선언만으로 끝 |
| 입력 검증 | Bean Validation | `@NotBlank`, `@Size`로 요청 검증 → `VALIDATION_FAILED` |
| 인증 · 권한 | Spring Security | 로그인, 비밀번호 BCrypt 해시, 요청별 권한 검사 |
| DB 스키마 관리 | Flyway | SQL 파일(`V1__init.sql`)로 스키마 변경 이력 관리. 서버가 뜰 때 자동 적용 |
| 로컬 DB | Docker Compose | MySQL을 컨테이너로 띄운다. Spring Boot가 `docker-compose.yml`을 보고 자동으로 실행 |
| 테스트 | JUnit 5, Spring Boot Test, Testcontainers | 진짜 MySQL 컨테이너로 Repository 테스트 |

### MySQL
가장 널리 쓰는 오픈소스 관계형 DB.

- 트랜잭션(InnoDB), 외래 키 `ON DELETE CASCADE / SET NULL`, 행 잠금(`SELECT … FOR UPDATE`)을 지원해 [ERD](../design/erd.md)의 규칙을 그대로 쓸 수 있다.
- 8.4가 LTS다. 문자셋은 `utf8mb4`(한글 · 이모지)로 둔다.

---

## 앱: Kotlin + Compose Multiplatform

### Kotlin
JetBrains가 만든 JVM 언어. Android 공식 언어다.

- **null 안전성**: `String`과 `String?`을 타입에서 구분해, null 오류를 컴파일 때 잡는다.
- **간결함**: `data class`(DTO 한 줄), 확장 함수, 기본 인자, 람다로 Java보다 코드가 짧다.
- **코루틴**: `suspend` 함수로 비동기 코드를 동기 코드처럼 위에서 아래로 쓴다. 서버 호출 중에도 화면이 멈추지 않는다.
- **멀티플랫폼(KMP)**: 같은 Kotlin 코드를 Android(JVM), iOS(네이티브), 웹으로 컴파일한다.

### Compose Multiplatform
Android의 Jetpack Compose를 iOS · 데스크톱 · 웹까지 넓힌 UI 프레임워크. JetBrains가 만든다.

- **선언형 UI**: React와 같은 개념. `@Composable` 함수가 상태를 받아 화면을 그리고, 상태가 바뀌면 다시 그린다 (리컴포지션). XML 레이아웃이 없다.
- **코드 공유**: 화면 · ViewModel · 네트워크 · DB 코드를 `commonMain`에 한 번 쓰고 Android와 iOS가 함께 쓴다. 플랫폼마다 다른 부분만 `expect`/`actual`로 나눈다.
- **네이티브 성능**: WebView가 아니라 각 플랫폼에서 직접 그린다 (Android는 Jetpack Compose 그대로, iOS는 Skia로 렌더링).
- **Android = Jetpack Compose**: Android 쪽은 구글 공식 Jetpack Compose와 같은 API라, Android 자료를 그대로 참고할 수 있다.
- **Compose Hot Reload**: 코드를 저장하면 앱을 다시 실행하지 않고 화면에 바로 반영한다 (데스크톱 미리보기 기준).
- **주의**: iOS 빌드 · 실행에는 Mac(Xcode)이 필요하다. 지금은 Android만 빌드한다.

### 함께 쓰는 라이브러리

[앱 컨벤션](../convention/app-convention.md#라이브러리)과 같다.

| 용도 | 라이브러리 | 특징 |
|---|---|---|
| 화면 이동 | Navigation Compose | 타입 안전한 라우트로 화면 이동 |
| 상태 | ViewModel + StateFlow | 화면 회전 등에도 상태 유지 |
| 서버 통신 | Ktor Client + kotlinx.serialization | 멀티플랫폼 HTTP 클라이언트, JSON ↔ data class |
| 의존성 주입 | Koin | 어노테이션 처리 없이 Kotlin DSL로 선언. 멀티플랫폼 지원 |
| 로컬 저장 | Room (KMP), DataStore | 오프라인 캐시, 로그인 토큰 · 설정값 |
| 서식 · 검사 | ktlint, detekt | 서식 자동 정리, 코드 냄새 검사 |

### 빌드: Gradle
백엔드와 앱 모두 Gradle(Kotlin DSL, `build.gradle.kts`)로 빌드한다.

- 의존성 버전은 `gradle/libs.versions.toml`(버전 카탈로그) 한 곳에서 관리한다.
- 프로젝트에 들어 있는 Gradle Wrapper(`./gradlew`)로 실행해 모두 같은 Gradle 버전을 쓴다. Gradle을 따로 설치하지 않는다.

## 참고

- [Spring Boot 버전 · EOL (versio.io)](https://www.versio.io/de/product-release-end-of-life-eol-broadcom-spring-boot.html)
- [Node.js Release Working Group](https://cdn.jsdelivr.net/gh/nodejs/release@main/README.md)
- [Compose Multiplatform 호환성 · 버전](https://kotlinlang.org/docs/multiplatform/compose-compatibility-and-versioning.html)
- [Vite 릴리스](https://vite.dev/blog/announcing-vite7)
