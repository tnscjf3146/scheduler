# 프론트엔드 컨벤션

출처: [React 프로젝트 코드 컨벤션 정리](https://llddang-blog.tistory.com/75)

React + TypeScript 기준. 패키지 매니저는 **pnpm**을 쓴다 (`npm`, `yarn`으로 설치하지 않는다). 들여쓰기, 따옴표, 세미콜론 같은 서식은 Prettier(`pnpm format`)에, 코드 규칙 검사는 oxlint(`pnpm lint`)에 맡기고 이 문서에는 적지 않는다.

## 스타일

- **Tailwind CSS v4**를 쓴다. 클래스는 JSX의 `className`에 바로 적는다.
- 색·간격·모서리·그림자·글자 스타일은 **디자인 토큰 유틸리티만** 쓴다 (`bg-bg-surface`, `p-md`, `text-heading-h2`). Tailwind 기본 팔레트는 지워 두었다.
- 임의값(`p-[13px]`, `bg-[#fff]`)은 쓰지 않는다. 필요한 값이 없으면 Figma와 `src/styles/global.css` 토큰에 먼저 추가한다.
- 여러 컴포넌트가 같이 쓰는 스타일 묶음은 `global.css`의 `@utility`로 만든다 (예: 레이어 `layer-card`). 한 컴포넌트에서만 쓰면 컴포넌트 안에 둔다.
- 토큰과 규칙: [프론트엔드 화면 명세 3장](../specs/frontend-spec.md), [레이어 구조](../specs/layer-system.md)

## 디렉토리 구조

기능(도메인) 단위로 컴포넌트를 나눈다.

```
src/
├── app/                     # 핵심 설정
│   ├── CompositeProvider.tsx   # 전역 Provider 조합
│   └── Router.tsx              # 라우팅
├── components/
│   ├── common/              # 공통 컴포넌트 (Button, Input, Modal …)
│   ├── layout/              # 레이아웃 (Header, Footer, Sidebar …)
│   └── features/{도메인}/    # 기능별 컴포넌트. 예: features/home/HomeBanner.tsx
├── lib/
│   ├── apis/                # API 함수 (*.api.ts)
│   ├── hooks/               # 커스텀 훅
│   └── utils/               # 유틸 함수 (*.util.ts)
├── pages/                   # 라우트별 페이지. 예: HomePage.tsx, dashboard/DashboardPage.tsx
├── contexts/                # Context API. 예: auth/auth.context.ts, auth.reducer.ts, AuthProvider.tsx
├── store/                   # 전역 상태 (*.slice.ts)
├── types/                   # 타입 (*.type.ts), dto/ (*.dto.ts)
├── data/                    # 상수 (*.constant.ts)
├── mocks/                   # 목업 데이터 (*.data.ts)
├── styles/
├── App.tsx
└── main.tsx
```

## 네이밍

- **디렉토리**: 위치와 상관없이 `kebab-case`.
- **컴포넌트 파일·컴포넌트 이름**: `PascalCase`. 다른 컴포넌트와 겹치지 않도록 도메인 이름을 앞에 붙인다. 예: 홈 화면의 공지사항 컴포넌트는 `HomeAnnouncement.tsx`
- **훅 파일**: `use`로 시작하는 `camelCase`. 예: `useAuth.ts`
- **그 외 파일**: `camelCase`에 역할 접미사를 붙인다.

| 종류 | 접미사 |
|---|---|
| API | `*.api.ts` |
| 유틸 | `*.util.ts` |
| Slice | `*.slice.ts` |
| Context | `*.context.ts` |
| Reducer | `*.reducer.ts` |
| 상수 | `*.constant.ts` |
| DTO | `*.dto.ts` |
| 타입 | `*.type.ts` |
| 목업 데이터 | `*.data.ts` |
| 테스트 | `*.test.ts` (대상 파일 옆에 둔다) |

## 테스트

- 로직(유틸, 계산)은 테스트를 둔다. 테스트 도구는 Node 내장 `node:test` + `node:assert`를 쓴다 (추가 라이브러리 없음).
- 실행: `pnpm test`. Jenkins가 `develop`·`main` 빌드마다 돌리고, 실패하면 배포하지 않는다.
- 테스트 파일은 브라우저 코드와 타입 설정이 달라 `tsconfig.node.json`에서 검사한다.

## API 함수명

- 조회(GET)는 `get`으로 시작한다. 예: `getAnnouncements`
- 변경(POST, PUT, PATCH, DELETE)은 `mutate`로 시작한다. 예: `mutateSignIn`

## 이벤트 핸들러

- 컴포넌트 안에서 선언하는 핸들러는 `handle + 대상 + 동작`. 예: `handleLikeButtonClick`
- props로 넘길 때 prop 이름은 `on + 대상 + 동작`. 예: `onLikeButtonClick`

```tsx
export default function Feed() {
  function handleLikeButtonClick() { ... }

  return <FeedCard onLikeButtonClick={handleLikeButtonClick} />;
}
```

## 함수 선언

- 컴포넌트와 일반 함수는 `function` 키워드로 선언한다. 호이스팅이 되고, 호출 스택에 함수 이름이 보이고, `const`로 선언한 상태 변수와 헷갈리지 않는다.
- 컴포넌트는 `export default function`으로 선언하고 props 타입을 `{컴포넌트명}Props`로 지정한다.
- 콜백은 화살표 함수를 쓴다. 예: `arr.map((n) => n * 2)`
