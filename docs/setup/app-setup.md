# 앱 세팅

Kotlin + Compose Multiplatform 앱(`app/`)을 처음부터 만들고 Android에서 실행하는 방법. 스택 설명은 [기술 스택](tech-stack.md#앱-kotlin--compose-multiplatform), 코드 규칙은 [앱 컨벤션](../convention/app-convention.md)을 본다.

## 1. 준비물

| 도구 | 설치 | 비고 |
|---|---|---|
| Android Studio | [developer.android.com/studio](https://developer.android.com/studio) 최신 안정 버전 | JDK가 함께 들어 있다 (Settings → Build Tools → Gradle → Gradle JDK에서 확인) |
| Kotlin Multiplatform 플러그인 | Android Studio → Settings → Plugins → "Kotlin Multiplatform" 설치 | KMP 프로젝트 실행 · 미리보기 |
| Android SDK · 에뮬레이터 | Android Studio → Device Manager에서 에뮬레이터 생성 (최신 API) | |
| Xcode (나중에) | Mac에서만 | iOS 빌드 시. 지금은 필요 없다 |

## 2. 프로젝트 만들기

[kmp.jetbrains.com](https://kmp.jetbrains.com) (Kotlin Multiplatform Wizard)에서 만든다. Android Studio의 **New Project → Kotlin Multiplatform**도 같은 마법사다.

| 항목 | 값 |
|---|---|
| Project Name | `scheduler` |
| Project ID | `com.scheduler` |
| 플랫폼 | **Android** 체크, **iOS** 체크 + "Share UI (with Compose Multiplatform)" |
| 그 외 (Desktop, Web, Server) | 체크하지 않는다 |

- iOS는 지금 빌드하지 않지만, 처음부터 체크해 두면 `iosMain`과 iOS 설정이 만들어져 나중에 붙이기 쉽다. Windows에서는 iOS 타깃 빌드만 건너뛴다.
- **Download** → 압축을 저장소의 `app/`에 푼다 → Android Studio에서 `app/` 폴더를 연다.

만들어지는 구조:

```
app/
├── composeApp/
│   └── src/
│       ├── commonMain/    # 공통 코드 (대부분 여기)
│       ├── androidMain/   # Android 전용 (MainActivity)
│       └── iosMain/       # iOS 전용 (나중에)
├── iosApp/                # Xcode 프로젝트 (나중에)
├── gradle/libs.versions.toml
├── build.gradle.kts
└── settings.gradle.kts
```

## 3. 라이브러리 추가

### `gradle/libs.versions.toml`

마법사가 만든 파일에 아래를 **추가**한다. 버전은 각 라이브러리 공식 문서에서 최신 안정 버전을 확인해 적는다 (`x.y.z` 자리).

```toml
[versions]
ktor = "x.y.z"
koin = "x.y.z"
navigation-compose = "x.y.z"      # org.jetbrains.androidx.navigation
kotlinx-serialization = "x.y.z"
room = "x.y.z"
sqlite = "x.y.z"
ksp = "x.y.z"                      # Kotlin 버전에 맞는 KSP
datastore = "x.y.z"
ktlint-gradle = "x.y.z"
detekt = "x.y.z"

[libraries]
ktor-client-core = { module = "io.ktor:ktor-client-core", version.ref = "ktor" }
ktor-client-content-negotiation = { module = "io.ktor:ktor-client-content-negotiation", version.ref = "ktor" }
ktor-serialization-kotlinx-json = { module = "io.ktor:ktor-serialization-kotlinx-json", version.ref = "ktor" }
ktor-client-okhttp = { module = "io.ktor:ktor-client-okhttp", version.ref = "ktor" }
ktor-client-darwin = { module = "io.ktor:ktor-client-darwin", version.ref = "ktor" }
koin-core = { module = "io.insert-koin:koin-core", version.ref = "koin" }
koin-compose-viewmodel = { module = "io.insert-koin:koin-compose-viewmodel", version.ref = "koin" }
koin-android = { module = "io.insert-koin:koin-android", version.ref = "koin" }
navigation-compose = { module = "org.jetbrains.androidx.navigation:navigation-compose", version.ref = "navigation-compose" }
kotlinx-serialization-json = { module = "org.jetbrains.kotlinx:kotlinx-serialization-json", version.ref = "kotlinx-serialization" }
room-runtime = { module = "androidx.room:room-runtime", version.ref = "room" }
room-compiler = { module = "androidx.room:room-compiler", version.ref = "room" }
sqlite-bundled = { module = "androidx.sqlite:sqlite-bundled", version.ref = "sqlite" }
datastore-preferences = { module = "androidx.datastore:datastore-preferences-core", version.ref = "datastore" }

[plugins]
kotlinSerialization = { id = "org.jetbrains.kotlin.plugin.serialization", version.ref = "kotlin" }
ksp = { id = "com.google.devtools.ksp", version.ref = "ksp" }
room = { id = "androidx.room", version.ref = "room" }
ktlint = { id = "org.jlleitschuh.gradle.ktlint", version.ref = "ktlint-gradle" }
detekt = { id = "io.gitlab.arturbosch.detekt", version.ref = "detekt" }
```

- ViewModel(`lifecycle-viewmodel-compose`)과 Material 3는 마법사가 이미 넣어 준다.

### 루트 `build.gradle.kts`

```kotlin
plugins {
    // 마법사가 넣은 플러그인들 …
    alias(libs.plugins.kotlinSerialization) apply false
    alias(libs.plugins.ksp) apply false
    alias(libs.plugins.room) apply false
    alias(libs.plugins.ktlint) apply false
    alias(libs.plugins.detekt) apply false
}
```

### `composeApp/build.gradle.kts`

```kotlin
plugins {
    // 마법사가 넣은 플러그인들 …
    alias(libs.plugins.kotlinSerialization)
    alias(libs.plugins.ksp)
    alias(libs.plugins.room)
    alias(libs.plugins.ktlint)
    alias(libs.plugins.detekt)
}

kotlin {
    sourceSets {
        commonMain.dependencies {
            implementation(libs.ktor.client.core)
            implementation(libs.ktor.client.content.negotiation)
            implementation(libs.ktor.serialization.kotlinx.json)
            implementation(libs.kotlinx.serialization.json)
            implementation(libs.koin.core)
            implementation(libs.koin.compose.viewmodel)
            implementation(libs.navigation.compose)
            implementation(libs.room.runtime)
            implementation(libs.sqlite.bundled)
            implementation(libs.datastore.preferences)
        }
        androidMain.dependencies {
            implementation(libs.ktor.client.okhttp)   // Android용 HTTP 엔진
            implementation(libs.koin.android)
        }
        iosMain.dependencies {
            implementation(libs.ktor.client.darwin)   // iOS용 HTTP 엔진
        }
        commonTest.dependencies {
            implementation(kotlin("test"))
        }
    }
}

room {
    schemaDirectory("$projectDir/schemas")
}

dependencies {
    // Room 코드 생성 (플랫폼마다)
    add("kspAndroid", libs.room.compiler)
    add("kspIosArm64", libs.room.compiler)
    add("kspIosSimulatorArm64", libs.room.compiler)
}
```

- 수정한 뒤 Android Studio 상단의 **Sync Now**를 누른다.

## 4. 설정

### API 주소

에뮬레이터에서 PC의 `localhost`는 `10.0.2.2`다.

```kotlin
// commonMain/kotlin/com/scheduler/core/network/ApiConfig.kt
expect val API_BASE_URL: String

// androidMain/…/ApiConfig.android.kt
actual val API_BASE_URL: String = "http://10.0.2.2:8080/api"
```

- 실제 기기로 테스트할 때는 PC의 IP(`http://192.168.x.x:8080/api`)로 바꾼다.

### 개발 중 HTTP 허용 (Android)

Android는 기본으로 `http://`를 막는다. **디버그 빌드에서만** 로컬 주소를 허용한다.

```xml
<!-- androidMain/res/xml/network_security_config.xml -->
<network-security-config>
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="false">10.0.2.2</domain>
    </domain-config>
</network-security-config>
```

`AndroidManifest.xml`의 `<application>`에 `android:networkSecurityConfig="@xml/network_security_config"`, 그리고 `<uses-permission android:name="android.permission.INTERNET" />`을 추가한다. 운영은 `https://`만 쓴다.

### Ktor 클라이언트

```kotlin
// commonMain/…/core/network/HttpClientFactory.kt
fun createHttpClient(): HttpClient = HttpClient {
    install(ContentNegotiation) {
        json(Json { ignoreUnknownKeys = true })   // 서버가 필드를 추가해도 앱이 깨지지 않게
    }
    defaultRequest { url(API_BASE_URL) }
    expectSuccess = true
}
```

### Koin 시작

```kotlin
// commonMain/…/di/AppModule.kt
val networkModule = module { single { createHttpClient() } }

// androidMain/…/SchedulerApplication.kt
class SchedulerApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        startKoin {
            androidContext(this@SchedulerApplication)
            modules(networkModule /*, issueModule, … */)
        }
    }
}
```

`AndroidManifest.xml`의 `<application android:name=".SchedulerApplication">`로 등록한다.

### ktlint · detekt

```kotlin
// composeApp/build.gradle.kts
detekt {
    buildUponDefaultConfig = true
    config.setFrom("$rootDir/config/detekt.yml")
}
```

`app/.editorconfig`에 Compose 함수 이름(PascalCase)을 ktlint가 허용하도록 적는다.

```ini
[*.{kt,kts}]
ktlint_function_naming_ignore_when_annotated_with = Composable
```

## 5. 폴더 만들기

[앱 컨벤션의 디렉토리 구조](../convention/app-convention.md#디렉토리-구조)대로 `commonMain/kotlin/com/scheduler/` 아래에 `di/`, `navigation/`, `core/`, `ui/theme/`, `ui/component/`, `feature/{issue,project,board,…}/`를 만든다.

## 6. 실행

| 방법 | 명령 |
|---|---|
| Android Studio | 상단 실행 구성에서 **composeApp** 선택 → 에뮬레이터 선택 → ▶ |
| 터미널: 디버그 APK 설치 | `./gradlew :composeApp:installDebug` |
| 테스트 · 검사 전체 | `./gradlew check` (ktlint, detekt, 테스트) |
| 서식 자동 정리 | `./gradlew ktlintFormat` |
| 화면 미리보기 | `@Preview` 함수 옆의 미리보기 패널 |

- 백엔드가 떠 있어야 API가 동작한다 → [백엔드 세팅](backend-setup.md#6-실행).
- Windows에서 iOS 관련 Gradle 작업은 건너뛰거나 경고만 난다. 무시해도 된다.

## 7. 나중에 iOS 붙이기

1. Mac에 Xcode 설치.
2. `iosApp/iosApp.xcodeproj`를 Xcode로 열거나, Android Studio(Mac)의 실행 구성에서 **iosApp** 선택.
3. `iosMain`에 `actual val API_BASE_URL`과 Koin 시작 코드를 넣는다 (`MainViewController.kt`).
4. Room · Ktor는 위에서 iOS 의존성(`ktor-client-darwin`, `kspIos…`)을 이미 넣어 두었다.

## 8. 문제 해결

| 증상 | 원인 · 해결 |
|---|---|
| `Cleartext HTTP traffic not permitted` | 네트워크 보안 설정이 빠졌다 (4. 설정 참고) |
| `Failed to connect to /10.0.2.2:8080` | 백엔드가 안 떴거나, 실제 기기에서 `10.0.2.2`를 썼다 (PC IP로 변경) |
| `Unresolved reference` (라이브러리) | Gradle Sync를 안 했다. **File → Sync Project with Gradle Files** |
| KSP · Room 컴파일 오류 | KSP 버전이 Kotlin 버전과 맞지 않는다. KSP 릴리스 페이지에서 짝을 확인 |
| Gradle JDK 오류 | Android Studio 설정의 Gradle JDK를 내장 JDK(jbr)로 지정 |
