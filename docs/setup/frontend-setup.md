# 프론트엔드 세팅

React + TypeScript + Vite 웹 프로젝트(`frontend/`)를 처음부터 만들고 실행하는 방법. 스택 설명은 [기술 스택](tech-stack.md#웹-react--typescript), 코드 규칙은 [프론트엔드 컨벤션](../convention/frontend-convention.md)을 본다.

## 1. 준비물

| 도구 | 설치 | 확인 |
|---|---|---|
| Node.js 24 LTS | [nodejs.org](https://nodejs.org)에서 LTS 설치, 또는 버전 관리자(Windows: `fnm`, macOS: `fnm`/`nvm`) | `node -v` → `v24.x` |
| pnpm | `corepack enable` (Node에 포함된 Corepack이 pnpm을 준비) | `pnpm -v` |
| 에디터 | VS Code + 확장: ESLint 대신 **oxc**, **Prettier**, **Tailwind CSS IntelliSense** | |

- 팀원 모두 같은 Node 메이저를 쓰도록 `frontend/.nvmrc`(또는 `.node-version`)에 `24`를 적는다.

## 2. 프로젝트 만들기

저장소 루트에서 실행한다.

```bash
pnpm create vite@latest frontend --template react-ts
cd frontend
pnpm install
```

`package.json`에 pnpm 버전을 고정한다 (Corepack이 이 버전을 쓴다).

```bash
corepack use pnpm@latest
```

## 3. 라이브러리 설치

```bash
# 라우팅, 서버 상태, 전역 상태
pnpm add react-router @tanstack/react-query @reduxjs/toolkit react-redux

# 드래그 앤 드롭, 차트
pnpm add @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities recharts

# 스타일 (Tailwind v4)
pnpm add -D tailwindcss @tailwindcss/vite

# 서식 · 검사
pnpm add -D prettier prettier-plugin-tailwindcss oxlint
```

- Vite 템플릿에 들어 있는 ESLint는 oxlint로 바꾼다: `pnpm remove eslint @eslint/js eslint-plugin-react-hooks eslint-plugin-react-refresh globals typescript-eslint` 후 `eslint.config.js`를 지운다.

## 4. 설정

### `vite.config.ts`

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    tsconfigPaths: true, // tsconfig의 paths(@/*)를 그대로 쓴다
  },
  server: {
    port: 5173,
    proxy: {
      // /api 요청을 로컬 Spring Boot로 넘긴다 (CORS 설정 없이 개발)
      "/api": "http://localhost:8080",
    },
  },
});
```

- `resolve.tsconfigPaths`는 Vite 8 옵션이다. 이전 버전이면 `vite-tsconfig-paths` 플러그인을 쓴다.

### `tsconfig.app.json` (추가할 부분)

```json
{
  "compilerOptions": {
    "strict": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  }
}
```

### `src/styles/global.css`

```css
@import "tailwindcss";

/* Tailwind 기본 팔레트를 지우고 디자인 토큰만 쓴다 (컨벤션: 스타일) */
@theme {
  --color-*: initial;
  --color-bg-surface: #ffffff;
  --color-text-primary: #172b4d;
  --spacing-md: 16px;
  /* … Figma 토큰을 여기에 추가 */
}
```

`src/main.tsx`에서 `import "@/styles/global.css";`로 불러온다.

### `.prettierrc`

```json
{
  "plugins": ["prettier-plugin-tailwindcss"]
}
```

### `package.json` 스크립트

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "lint": "oxlint",
    "format": "prettier --write .",
    "test": "node --test \"src/**/*.test.ts\""
  }
}
```

- 테스트는 Node 내장 `node:test`를 쓴다. Node 24는 `.ts`를 바로 실행하므로 변환 도구가 필요 없다 (타입 검사는 `tsc -b`가 한다).

### `.env`

```bash
# .env.development
VITE_API_BASE_URL=/api
```

- `VITE_`로 시작하는 값만 브라우저 코드에서 `import.meta.env.VITE_API_BASE_URL`로 읽힌다. 비밀 값은 넣지 않는다.

## 5. 폴더 만들기

[컨벤션의 디렉토리 구조](../convention/frontend-convention.md#디렉토리-구조)대로 만든다.

```bash
mkdir -p src/app src/components/common src/components/layout src/components/features \
  src/lib/apis src/lib/hooks src/lib/utils src/pages src/contexts src/store \
  src/types/dto src/data src/mocks src/styles
```

API 호출은 `fetch`를 감싼 공통 함수 하나로 한다.

```ts
// src/lib/apis/client.ts
const BASE_URL = import.meta.env.VITE_API_BASE_URL;

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    credentials: "include",
  });
  if (!res.ok) throw await res.json(); // { code, message, fieldErrors }
  return res.status === 204 ? (undefined as T) : res.json();
}
```

## 6. 실행

```bash
pnpm dev        # http://localhost:5173
pnpm build      # dist/ 생성
pnpm lint
pnpm format
pnpm test
```

- 백엔드를 함께 띄워야 API가 동작한다 → [백엔드 세팅](backend-setup.md#6-실행).

## 7. 문제 해결

| 증상 | 원인 · 해결 |
|---|---|
| `pnpm: command not found` | `corepack enable`을 안 했다. 관리자 권한 터미널에서 다시 실행 |
| API 요청이 404 | 경로가 `/api`로 시작하는지, 백엔드가 8080에서 떠 있는지 확인 |
| Tailwind 클래스가 안 먹음 | `global.css`를 `main.tsx`에서 import했는지, `@tailwindcss/vite` 플러그인을 넣었는지 확인 |
| `@/` import 오류 | `tsconfig.app.json`의 `paths`와 `vite.config.ts`의 `tsconfigPaths` 둘 다 확인 |
