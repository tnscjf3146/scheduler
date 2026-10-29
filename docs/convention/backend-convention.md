# 백엔드 컨벤션

## 백엔드 패키지 구조

- **기능(도메인) 단위**로 패키지를 나눈다: `com.scheduler.issue`, `com.scheduler.project` …
- 각 기능 패키지 안에 Controller, Service, Repository, 엔티티를 함께 둔다. `controller/`, `service/` 같은 계층별 최상위 패키지는 만들지 않는다.
- 해당 패키지 안에서만 쓰는 클래스는 `public`을 빼서 package-private으로 둔다.
- 여러 기능이 함께 쓰는 설정, 예외, 유틸은 `com.scheduler.common`에 둔다.

## 에러 처리

- API 에러는 `com.scheduler.common.error.ApiException`을 던진다. 예: `throw new ApiException(ErrorCode.NOT_FOUND)`
- 응답 모양(`{ code, message, fieldErrors, retryAfterSeconds }`)은 `GlobalExceptionHandler`가 한 곳에서 만든다. 컨트롤러에서 에러 응답을 직접 만들지 않는다.
- 에러 코드는 `ErrorCode`에 둔다. 기능별 코드(예: `PROJECT_KEY_INVALID`)는 그 기능을 만들 때 추가하고, [API 명세 9장](../design/spec/api-spec.md#9-에러-코드)과 맞춘다.
- 요청 본문 검증은 `@Valid` + Bean Validation(`@NotBlank`, `@Size` …)으로 하면 `VALIDATION_FAILED`와 필드별 이유가 자동으로 나간다.
- 예상하지 못한 오류는 `INTERNAL_ERROR`로 응답하고, 내부 내용은 로그에만 남긴다.

## Java 코딩 컨벤션

출처: [캠퍼스 핵데이 Java 코딩 컨벤션](https://naver.github.io/hackday-conventions-java/)

### 파일
- UTF-8 인코딩, 줄바꿈은 LF, 파일 끝에 개행 문자.

### 이름
- 식별자는 영문, 숫자, `_`만 사용. 한국어 발음을 영문으로 옮긴 이름 금지 (예: `moksu` ✗). 고유명사는 예외.
- 약어도 카멜 케이스로 쓴다: `HttpApiUrl` (`HTTPAPIURL` ✗).
- 패키지: 전부 소문자, `_`나 대문자 없이.
- 클래스·인터페이스: `UpperCamelCase`. 클래스는 명사, 인터페이스는 명사나 형용사.
- 테스트 클래스는 `Test`로 끝난다.
- 메서드: `lowerCamelCase`, 동사로 시작. 변환·빌더 메서드는 전치사로 시작 가능 (`toString`, `withUserId`). 테스트 메서드에는 `_` 허용.
- 상수(불변 타입의 `static final` 필드): `UPPER_SNAKE_CASE`.
- 변수·필드·파라미터: `lowerCamelCase`. 한 글자 이름은 반복문 인덱스나 람다 파라미터처럼 잠깐 쓰는 변수에만.

### 선언
- 소스 파일 하나에 최상위 클래스 하나.
- `import *` 금지. static import는 예외.
- 제한자 순서: `public protected private abstract static final transient volatile synchronized native strictfp`
- 클래스·메서드·생성자의 어노테이션은 한 줄에 하나씩. 파라미터 없는 어노테이션 하나뿐이면 선언과 같은 줄에 써도 된다.
- 한 줄에 문장 하나, 선언 하나에 변수 하나.
- 배열 대괄호는 타입 뒤에: `String[] names`
- `long` 리터럴은 대문자 `L`: `10L`
- 특수 문자는 `\n`, `\t`처럼 이스케이프로 쓴다. 8진수·유니코드 이스케이프 금지.

### 들여쓰기·중괄호
- 들여쓰기는 **하드탭**, 탭 너비 4. 블록마다 한 단계씩.
- K&R 스타일: 여는 `{`는 줄 끝에, 닫는 `}`는 단독 줄에.
- `else`, `catch`, `finally`, do-while의 `while`은 `}`와 같은 줄에.
- 빈 블록은 `{}`로 써도 된다.
- `if`, `for` 같은 제어문은 한 줄이라도 중괄호 필수.

### 줄 길이·줄바꿈
- 한 줄 최대 **120자**.
- `package`, `import` 문은 줄바꿈하지 않는다.
- 이어지는 줄은 최소 한 단계 더 들여쓴다.
- 줄바꿈 위치: `extends`·`implements`·`throws` 뒤, 여는 `(` 뒤, `,` 뒤, `.` 앞, 연산자 앞.

### 빈 줄
- `package` 문 다음에 빈 줄.
- import 그룹 순서: static → `java.` → `javax.` → `org.` → `net.` → 기타 `com.*` → 그 외 패키지 → `com.nhncorp.` → `com.navercorp.` → `com.naver.`. 그룹 사이에는 빈 줄, 그룹 안에서는 알파벳순.
- 메서드 사이에 빈 줄.

### 공백
- 줄 끝 공백·탭 금지 (빈 줄 포함).
- `if`, `for`, `while`, `catch`, `synchronized`, `switch` 키워드와 `(` 사이에 공백.
- 메서드·생성자·어노테이션 이름과 `(` 사이에는 공백 없음.
- `{` 앞, `}`와 `else`/`catch` 사이에 공백.
- 닫는 `]` 뒤에 공백 (다음 문자가 `;`이면 생략): `new int[] {0, 1}`
- 형변환 괄호 안에는 공백 없음: `(String)obj`
- 제네릭: `<` 뒤와 `>` 앞에는 공백 없음.
- `,`와 for문 `;` 뒤에 공백, 앞에는 없음.
- 이항·삼항 연산자 양옆, 향상된 for문과 삼항 연산자의 `:` 양옆에 공백.
- 단항 연산자(`++`, `--`, `!`)와 피연산자 사이에는 공백 없음.
- 주석: 줄 끝 `//` 앞, `//`와 `/*` 뒤, `*/` 앞에 공백.
