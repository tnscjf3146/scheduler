# 백엔드 세팅

Java + Spring Boot API 서버(`backend/`)를 처음부터 만들고 실행하는 방법. 스택 설명은 [기술 스택](tech-stack.md#백엔드-java--spring-boot), 코드 규칙은 [백엔드 컨벤션](../convention/backend-convention.md), 테이블은 [ERD](../design/erd.md)를 본다.

## 1. 준비물

| 도구 | 설치 | 확인 |
|---|---|---|
| JDK 25 | [Eclipse Temurin](https://adoptium.net) 25 LTS. `JAVA_HOME` 설정 | `java -version` → `25` |
| Docker Desktop | [docker.com](https://www.docker.com/products/docker-desktop/). 로컬 MySQL용 | `docker compose version` |
| IDE | IntelliJ IDEA (Community도 가능) | |

- Gradle은 설치하지 않는다. 프로젝트의 `./gradlew`(Wrapper)를 쓴다.
- Windows는 PowerShell에서 `./gradlew` 대신 `.\gradlew.bat`을 쓴다.

## 2. 프로젝트 만들기

[start.spring.io](https://start.spring.io)에서 아래처럼 고르고 **Generate** → 압축을 저장소의 `backend/`에 푼다.

| 항목 | 값 |
|---|---|
| Project | Gradle - Kotlin |
| Language | Java |
| Spring Boot | 4.x 중 최신 안정 버전 (SNAPSHOT, M, RC 제외) |
| Group | `com` |
| Artifact | `scheduler` |
| Package name | `com.scheduler` |
| Packaging | Jar |
| Java | 25 |

Dependencies:

| 의존성 | 용도 |
|---|---|
| Spring Web | REST API |
| Spring Data JPA | DB 접근 |
| Validation | 요청 검증 (`@Valid`) |
| Spring Security | 로그인, 권한 |
| MySQL Driver | MySQL 연결 |
| Flyway Migration | 스키마 관리 |
| Docker Compose Support | 실행 시 로컬 MySQL 자동 기동 |
| Testcontainers | 테스트용 MySQL 컨테이너 |
| Lombok | 반복 코드(getter, 생성자) 줄이기 (선택) |

- IntelliJ에서는 **New Project → Spring Boot**로 같은 설정을 고를 수 있다.

## 3. 로컬 DB

저장소 루트에 `docker-compose.yml`을 둔다 (웹·앱 개발자도 같은 DB를 띄울 수 있게).

```yaml
services:
  mysql:
    image: mysql:8.4
    environment:
      MYSQL_DATABASE: scheduler
      MYSQL_USER: scheduler
      MYSQL_PASSWORD: scheduler
      MYSQL_ROOT_PASSWORD: root
      TZ: UTC
    command:
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_unicode_ci
    ports:
      - "3306:3306"
    volumes:
      - mysql-data:/var/lib/mysql

volumes:
  mysql-data:
```

- 비밀번호는 로컬 전용 값이다. 운영 값은 환경 변수로 넣고 저장소에 올리지 않는다.
- Docker Compose Support가 이 파일을 찾도록 `application.yml`에 경로를 적는다 (아래).

## 4. 설정

### `src/main/resources/application.yml`

```yaml
spring:
  application:
    name: scheduler
  docker:
    compose:
      file: ../docker-compose.yml   # 서버를 켜면 MySQL 컨테이너도 자동으로 켠다
  datasource:
    url: jdbc:mysql://localhost:3306/scheduler?serverTimezone=UTC
    username: scheduler
    password: scheduler
  jpa:
    hibernate:
      ddl-auto: validate            # 스키마는 Flyway가 만든다. JPA는 검사만
    open-in-view: false
    properties:
      hibernate:
        jdbc:
          time_zone: UTC            # 모든 시간 UTC 저장 (ERD 공통 규칙)
  flyway:
    enabled: true
  threads:
    virtual:
      enabled: true                 # 가상 스레드

server:
  port: 8080
  servlet:
    context-path: /api              # 모든 API는 /api로 시작
```

- 운영 설정은 `application-prod.yml`로 나누고 `SPRING_PROFILES_ACTIVE=prod`로 켠다. 접속 정보는 `${DB_URL}`처럼 환경 변수로 받는다.

### Flyway 마이그레이션

ERD를 SQL로 옮겨 `src/main/resources/db/migration/V1__init.sql`에 둔다. 이후 스키마 변경은 `V2__add_xxx.sql`처럼 **새 파일로 추가**하고, 이미 적용된 파일은 고치지 않는다.

```sql
-- V1__init.sql (일부)
CREATE TABLE users (
    id            BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
    email         VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    name          VARCHAR(50)  NOT NULL,
    created_at    DATETIME(6)  NOT NULL,
    updated_at    DATETIME(6)  NOT NULL
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
-- … projects, project_members, statuses, issue_types, sprints, issues, …
```

- [ERD의 DBML](../design/erd.md#dbml)을 dbdiagram.io에 붙여 넣고 **Export → MySQL**로 SQL 초안을 뽑을 수 있다. Enum 컬럼은 `VARCHAR(20)`으로, FK의 `ON DELETE`는 ERD 표대로 맞춘다.

### 시간대 (UTC)

`SchedulerApplication`의 `main`에서 JVM 기본 시간대를 UTC로 고정한다.

```java
public static void main(String[] args) {
	TimeZone.setDefault(TimeZone.getTimeZone("UTC"));
	SpringApplication.run(SchedulerApplication.class, args);
}
```

### JPA Auditing (`created_at`, `updated_at`)

```java
@Configuration
@EnableJpaAuditing
class JpaConfig {
}
```

엔티티는 공통 부모(`BaseTimeEntity`)에 `@CreatedDate`, `@LastModifiedDate`를 두고 상속한다.

### 에디터 설정 (`backend/.editorconfig`)

[백엔드 컨벤션](../convention/backend-convention.md#들여쓰기중괄호)의 하드탭 · 줄 길이를 IDE에 알려준다.

```ini
root = true

[*.java]
indent_style = tab
indent_size = 4
max_line_length = 120
end_of_line = lf
insert_final_newline = true
charset = utf-8
```

### Lombok을 쓸 때

- IntelliJ: **Settings → Build → Compiler → Annotation Processors → Enable annotation processing** 켜기.
- 엔티티에는 `@Getter`, `@NoArgsConstructor(access = AccessLevel.PROTECTED)`만 쓰고 `@Setter`, `@Data`는 쓰지 않는다 (아무 데서나 값이 바뀌지 않게).

## 5. 패키지 만들기

[컨벤션의 패키지 구조](../convention/backend-convention.md#백엔드-패키지-구조)대로 기능 단위로 만든다.

```
src/main/java/com/scheduler/
├── SchedulerApplication.java
├── common/
│   ├── config/        # JpaConfig, SecurityConfig, WebConfig(CORS)
│   ├── entity/        # BaseTimeEntity
│   └── error/         # ApiException, ErrorCode, GlobalExceptionHandler
├── user/
├── project/
├── issue/
├── sprint/
├── comment/
├── notification/
└── dashboard/
```

## 6. 실행

```bash
cd backend
./gradlew bootRun          # MySQL 컨테이너 자동 기동 + Flyway 적용 + 서버 실행 (http://localhost:8080/api)
./gradlew test             # 테스트 (Testcontainers가 테스트용 MySQL을 따로 띄운다)
./gradlew build            # build/libs/scheduler-*.jar 생성
java -jar build/libs/scheduler-0.0.1-SNAPSHOT.jar
```

- IntelliJ에서는 `SchedulerApplication`의 실행 버튼을 누른다.
- 처음 실행하면 MySQL 이미지를 내려받느라 시간이 걸린다.

## 7. 웹 · 앱과 연결

| 클라이언트 | 연결 방법 |
|---|---|
| 웹 개발 서버 (`localhost:5173`) | Vite 프록시가 `/api`를 8080으로 넘겨 CORS 설정이 필요 없다 |
| Android 에뮬레이터 | `http://10.0.2.2:8080/api` (에뮬레이터에서 PC의 localhost) |
| 실제 Android 기기 | 같은 Wi-Fi의 PC IP(`http://192.168.x.x:8080/api`) |

- 웹을 다른 도메인에 배포하면 `WebConfig`에서 그 도메인만 CORS를 허용한다.

## 8. 문제 해결

| 증상 | 원인 · 해결 |
|---|---|
| `Communications link failure` | MySQL이 안 떴다. Docker Desktop 실행 여부, 3306 포트를 다른 MySQL이 쓰는지 확인 |
| `Schema-validation: missing table` | Flyway SQL과 엔티티가 다르다. 엔티티를 고쳤으면 `V{n}__…sql`도 추가 |
| `Validate failed: Migration checksum mismatch` | 이미 적용된 마이그레이션 파일을 고쳤다. 되돌리고 새 버전 파일로 추가 (로컬이면 `docker compose down -v`로 DB 초기화) |
| 모든 요청이 401/403 | Spring Security 기본 설정이 전부 막는다. `SecurityConfig`에서 회원가입 · 로그인 경로를 허용 |
| 시간이 9시간 어긋남 | JVM · JDBC · MySQL 중 하나가 KST다. 위 UTC 설정 세 곳 확인 |
