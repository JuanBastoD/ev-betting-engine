# Frontend Operational Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single-screen React operational panel (`frontend/`) that lets the solo operator browse detected value bets with filters, trigger the pipeline on demand, and settle bets — talking to the existing FastAPI backend over HTTP with no backend logic changes beyond CORS.

**Architecture:** Standalone Vite + React + TypeScript SPA in `frontend/`, using TanStack Query for all server state (no Redux, no router — one screen). A thin typed fetch client (`src/api/client.ts`) wraps `fetch`, and `src/api/types.ts` mirrors the FastAPI Pydantic schemas field-for-field. Four presentational/self-contained components (`RunPipelineBar`, `ValueBetFilters`, `ValueBetTable`, `SettleBetModal`) compose into one `App.tsx`.

**Tech Stack:** Vite, React 18/19 (whatever `npm create vite@latest` scaffolds), TypeScript, `@tanstack/react-query`, Vitest, `@testing-library/react`, `msw` (Mock Service Worker) for HTTP mocking in tests. Backend: FastAPI's `CORSMiddleware`, no new Python dependency.

## Global Constraints

- Design spec: [docs/superpowers/specs/2026-07-06-frontend-panel-design.md](../specs/2026-07-06-frontend-panel-design.md) — every task below traces back to a section there.
- Node.js >= 20.19 or >= 22.12 required to run Vite (check with `node --version` before Task 2).
- Frontend npm packages are installed via `@latest` at scaffold/install time — the resulting `package-lock.json` pins whatever resolves at that moment. Don't hand-pin different versions afterward without a concrete reason (a real incompatibility hit during install/build).
- No `globals: true` in the Vitest config — every test file explicitly imports `describe`/`it`/`expect`/etc. from `"vitest"`, matching this codebase's existing explicit-imports convention (see `CLAUDE.md`'s testing conventions section).
- TypeScript types in `frontend/src/api/types.ts` are exact snake_case mirrors of the Pydantic schemas in `src/presentation/api/schemas.py` — no camelCase conversion layer, no fields invented that the API doesn't return.
- `frontend/` is a fully standalone npm project — no shared build tooling/config with the Python backend beyond living in the same git repo. The only backend change in this plan is CORS (Task 1).
- HTTP is always mocked with `msw`'s `setupServer` (Node integration) in frontend tests, never a real network call — mirrors the backend's own `respx` convention (mock at the HTTP boundary).
- **Every frontend task must pass `npm run build` (which runs `tsc -b && vite build`), not only `npm run test`.** Vitest transpiles via esbuild and does NOT type-check, so a `tsc` error (e.g. an unused import under `noUnusedLocals: true`) can pass tests while breaking the build. Run `npm run build` (or at least `npx tsc -b`) before committing any frontend task, and treat a type error as a task failure.
- Calibration report / correction-factor recompute / multi-page routing are explicitly out of scope (deferred per the design spec) — do not add them opportunistically while implementing these tasks.

---

### Task 1: Backend CORS support

**Files:**
- Modify: `src/infrastructure/config.py`
- Modify: `src/presentation/api/app.py`
- Modify: `tests/infrastructure/test_config.py`
- Modify: `tests/presentation/api/test_app.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `Settings.cors_allowed_origins: list[str]` (default `["http://localhost:5173"]`, env var `CORS_ALLOWED_ORIGINS`, comma-separated) — consumed by `create_app()` in `app.py`. No other task depends on this beyond the frontend's dev server needing its origin allowed.

- [ ] **Step 1: Write the failing config tests**

Open `tests/infrastructure/test_config.py`. Add `"CORS_ALLOWED_ORIGINS"` to the `_isolate_env` fixture's tuple of env vars to delete:

```python
@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "DATABASE_URL",
        "ODDS_API_KEY",
        "ODDS_API_BASE_URL",
        "SPORTMONKS_API_TOKEN",
        "SPORTMONKS_BASE_URL",
        "KELLY_FRACTION",
        "MIN_EV_THRESHOLD",
        "SHARP_BOOKMAKER",
        "SPORT_KEY",
        "LOCAL_BOOKMAKER",
        "LEAGUE_AVERAGE_GOALS",
        "MATCH_CONFIRMATION_MODE",
        "MARKET_WEIGHT",
        "PIPELINE_INTERVAL_SECONDS",
        "CORS_ALLOWED_ORIGINS",
    ):
        monkeypatch.delenv(key, raising=False)
```

In `test_settings_applies_defaults_for_optional_values`, add this assertion at the end of the function body:

```python
    assert settings.cors_allowed_origins == ["http://localhost:5173"]
```

In `test_settings_reads_overridden_values_from_env`, add this line among the other `monkeypatch.setenv(...)` calls:

```python
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://panel.example.com")
```

and add this assertion among the others at the end:

```python
    assert settings.cors_allowed_origins == ["https://panel.example.com"]
```

Append this new test at the end of the file:

```python
def test_settings_parses_comma_separated_cors_origins(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch)
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS", "http://localhost:5173,https://panel.example.com"
    )

    settings = Settings()

    assert settings.cors_allowed_origins == [
        "http://localhost:5173",
        "https://panel.example.com",
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/infrastructure/test_config.py -v --no-cov`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'cors_allowed_origins'` (or a pydantic validation error, since the field doesn't exist yet).

- [ ] **Step 3: Add the field to `Settings`**

> **Why `NoDecode`:** pydantic-settings' `EnvSettingsSource` JSON-decodes the
> raw env string of any `list[...]`-typed field *before* any
> `field_validator(mode="before")` runs. Without `NoDecode`, a plain
> comma-separated `CORS_ALLOWED_ORIGINS=a,b` raises a `JSONDecodeError`
> instead of reaching `_split_cors_origins`. `Annotated[list[str], NoDecode]`
> disables that pre-decode so the raw string reaches the validator. (The
> default value is not run through the validator unless the env var is set,
> and it is already a `list`, so it needs no splitting.) This is confirmed
> working against the project's `pydantic-settings==2.14.2`.

Open `src/infrastructure/config.py`. It currently starts with:

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
```

Change those two lines to:

```python
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
```

Add this field at the end of the class body (after `calibration_min_sample_size`):

```python
    # --- Frontend panel (CORS) ---
    # Comma-separated list of origins the browser-based panel is served
    # from - split explicitly rather than relying on pydantic-settings'
    # JSON-array env parsing, since a plain comma list is what a human
    # editing .env will actually type. NoDecode disables the JSON pre-decode
    # so the raw string reaches _split_cors_origins (see the note above).
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:5173"], alias="CORS_ALLOWED_ORIGINS"
    )

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/infrastructure/test_config.py -v --no-cov`
Expected: PASS (all tests in the file, including the three you modified/added).

- [ ] **Step 5: Write the failing CORS middleware test**

Open `tests/presentation/api/test_app.py`. Add `import httpx` and the `Settings` import to the imports at the top (alongside the existing `from unittest.mock import MagicMock, patch` and `import pytest`):

```python
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.infrastructure.config import Settings
from src.infrastructure.persistence import session as session_module
from src.presentation.api.app import create_app, lifespan
```

Append these two tests at the end of the file:

```python
async def test_cors_allows_configured_frontend_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    # A NON-default origin plus a freshly-constructed Settings injected into
    # create_app() is what proves the middleware reads the *configured* value
    # rather than a hardcoded default. get_settings() is @lru_cache'd, so
    # relying on it here would hand back a stale cached instance and mask the
    # wiring; and using the default origin would pass even if the value were
    # hardcoded. See create_app()'s `settings` parameter (Step 7).
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://panel.example.com")
    app = create_app(settings=Settings())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/health", headers={"Origin": "https://panel.example.com"}
        )

    assert response.headers["access-control-allow-origin"] == "https://panel.example.com"


async def test_cors_omits_header_for_disallowed_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://panel.example.com")
    app = create_app(settings=Settings())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/health", headers={"Origin": "https://evil.example.com"}
        )

    assert "access-control-allow-origin" not in response.headers
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/presentation/api/test_app.py -v --no-cov`
Expected: FAIL — `test_cors_allows_configured_frontend_origin` fails with `KeyError: 'access-control-allow-origin'`, and `create_app(settings=...)` raises a `TypeError` for the unexpected keyword argument (no CORS middleware and no `settings` parameter yet).

- [ ] **Step 7: Add `CORSMiddleware` to `create_app()`**

Open `src/presentation/api/app.py`. Add the `CORSMiddleware` import alongside the existing `fastapi` import, and the `Settings` import alongside the other `src.infrastructure` imports:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
```

```python
from src.infrastructure.config import Settings
```

Change `create_app()` from:

```python
def create_app() -> FastAPI:
    app = FastAPI(title="ev-betting-engine", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(pipeline.router)
    app.include_router(value_bets.router)
    app.include_router(calibration.router)
    return app
```

to:

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    # settings is injectable so a test can construct the app against a
    # fresh, non-cached Settings and prove the CORS origins come from
    # configuration. In production it's None and resolves to the cached
    # get_settings() singleton (env is stable for the process lifetime).
    if settings is None:
        settings = get_settings()
    app = FastAPI(title="ev-betting-engine", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(pipeline.router)
    app.include_router(value_bets.router)
    app.include_router(calibration.router)
    return app
```

`get_settings` is already imported in this file (used inside `lifespan`), so no new import is needed for it.

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/presentation/api/test_app.py -v --no-cov`
Expected: PASS (all tests in the file).

- [ ] **Step 9: Document the new setting in `.env.example`**

Open `.env.example`. Append at the end of the file:

```
# Comma-separated list of origins allowed to call this API from a browser
# (CORS). The frontend panel's Vite dev server runs on 5173 by default -
# if Vite picks a different port because 5173 is busy, add that origin
# here too.
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

- [ ] **Step 10: Run the full backend suite**

Run: `uv run pytest`
Expected: PASS, 0 warnings, coverage table shows no new gaps (the new field/branch in `config.py` and the new middleware line in `app.py` are both covered by the tests above).

- [ ] **Step 11: Commit**

```bash
git add src/infrastructure/config.py src/presentation/api/app.py tests/infrastructure/test_config.py tests/presentation/api/test_app.py .env.example
git commit -m "feat(api): add configurable CORS support for the frontend panel"
```

---

### Task 2: Scaffold the Vite + React + TypeScript project

**Files:**
- Create: `frontend/` (via `npm create vite@latest`)
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx` (new)
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/setupTests.ts`
- Create: `frontend/src/test/server.ts`
- Create: `frontend/.env.example`
- Modify: `frontend/package.json` (scripts)
- Modify: `.gitignore` (repo root)
- Delete: `frontend/src/App.css`, `frontend/src/assets/react.svg`

**Interfaces:**
- Produces: a working `npm run dev` / `npm run build` / `npm run test` toolchain in `frontend/`, an `App` component (`frontend/src/App.tsx`, default export) rendering an `<h1>Panel Operativo</h1>`, and `frontend/src/test/server.ts` exporting `server: SetupServerApi` (from `msw/node`) that every later test file imports and calls `server.use(...)` on.

- [ ] **Step 1: Confirm Node version**

Run: `node --version`
Expected: `v20.19.x` or higher (or `v22.12.x` or higher). If lower, stop and upgrade Node before continuing — Vite 8 will refuse to run otherwise.

- [ ] **Step 2: Add frontend build artifacts to `.gitignore`**

Open `.gitignore` (repo root). Append at the end:

```

# Frontend (frontend/) build artifacts
frontend/node_modules/
frontend/dist/
frontend/.env
```

- [ ] **Step 3: Scaffold the project**

Run (from the repo root, `C:\Users\Juanes\Documents\BETTING`):

```bash
npm create vite@latest frontend -- --template react-ts
```

Expected: a `frontend/` directory is created with `package.json`, `vite.config.ts`, `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/App.css`, `src/index.css`, `src/assets/react.svg`, `public/vite.svg`.

- [ ] **Step 4: Install base dependencies**

Run:

```bash
cd frontend && npm install
```

Expected: `node_modules/` created, `package-lock.json` created, no errors.

- [ ] **Step 5: Install testing dependencies**

Run (still inside `frontend/`):

```bash
npm install -D vitest @testing-library/react @testing-library/dom @testing-library/jest-dom @testing-library/user-event jsdom msw
```

Expected: all six packages added to `devDependencies` in `package.json`, no errors.

- [ ] **Step 6: Install TanStack Query**

Run (still inside `frontend/`):

```bash
npm install @tanstack/react-query
```

Expected: added to `dependencies` in `package.json`.

- [ ] **Step 7: Add test scripts to `package.json`**

Open `frontend/package.json`. In the `"scripts"` object, add two entries (keep the existing `dev`/`build`/`lint`/`preview` scripts as-is):

```json
    "test": "vitest run",
    "test:watch": "vitest"
```

- [ ] **Step 8: Configure Vitest in `vite.config.ts`**

Open `frontend/vite.config.ts`. It currently looks like:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
})
```

Change it to:

```typescript
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
  },
})
```

- [ ] **Step 9: Create the shared MSW server**

Create `frontend/src/test/server.ts`:

```typescript
import { setupServer } from "msw/node";

export const server = setupServer();
```

- [ ] **Step 10: Create the Vitest setup file**

Create `frontend/src/setupTests.ts`:

```typescript
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./test/server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
// React Testing Library's automatic per-test cleanup only self-registers
// when `afterEach` is a global, which it is not under `globals: false`.
// Call it explicitly here so component tests don't leak mounted DOM into
// each other (otherwise a second render() duplicates roles/text and breaks
// getByRole/getByText queries).
afterEach(() => {
  server.resetHandlers();
  cleanup();
});
afterAll(() => server.close());
```

> **Note (added during execution):** the `cleanup()` call above is required
> precisely because this project runs with `globals: false`. Every component
> test file below (Tasks 6-9) relies on this shared cleanup and must NOT add
> its own `afterEach(cleanup)`.

- [ ] **Step 11: Remove the default Vite demo content**

Run (inside `frontend/`):

```bash
rm src/App.css src/assets/react.svg
```

Replace `frontend/src/App.tsx` entirely with:

```tsx
function App() {
  return (
    <main>
      <h1>Panel Operativo</h1>
    </main>
  );
}

export default App;
```

Open `frontend/src/main.tsx`. It currently imports `'./index.css'` and `App` and renders `<App />` inside `<StrictMode>` — leave `main.tsx` as-is for now (Task 4 modifies it to add the query client provider).

- [ ] **Step 12: Write the smoke test**

Create `frontend/src/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("renders the panel title", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Panel Operativo" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 13: Run the test to verify it passes**

Run (inside `frontend/`): `npm run test`
Expected: PASS — 1 test file, 1 test passed.

- [ ] **Step 14: Verify the build and dev server work**

Run (inside `frontend/`): `npm run build`
Expected: completes with no TypeScript errors, produces `frontend/dist/`.

- [ ] **Step 15: Commit**

```bash
git add frontend .gitignore
git commit -m "feat(frontend): scaffold Vite/React/TypeScript project with Vitest and MSW"
```

---

### Task 3: API types and typed HTTP client

**Files:**
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/client.ts`
- Test: `frontend/src/api/client.test.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure new module), but its shape mirrors `src/presentation/api/schemas.py`'s `ValueBetSchema`/`ValueBetListResponse`/`PipelineRunResponse`/`SettleBetRequest`/`SettleBetResponse`/`ErrorResponse`.
- Produces: `ApiError` (class, has `.status: number` and `.message`), `NetworkError` (class, has `.message`), `apiGet<T>(path: string): Promise<T>`, `apiPost<T>(path: string, body?: unknown): Promise<T>` — every later task's API calls go through these two functions. Also produces the types `MarketType`, `ModelSource`, `BetResult`, `ValueBet`, `ValueBetListResponse`, `ValueBetFilters`, `PipelineRunResponse`, `SettleBetRequest`, `SettleBetResponse`, `ApiErrorBody` from `types.ts`.

- [ ] **Step 1: Write the types file**

Create `frontend/src/api/types.ts`:

```typescript
export type MarketType = "MATCH_WINNER_1X2" | "OVER_UNDER" | "BTTS" | "PLAYER_PROP";

export type ModelSource = "MARKET" | "STATISTICAL" | "BOTH" | "PLAYER_PROPS";

export type BetResult = "WON" | "LOST" | "PUSH";

export interface ValueBet {
  match_id: string;
  league_id: string;
  market_type: MarketType;
  outcome: string;
  line: number | null;
  local_odds: number;
  fair_probability: number;
  edge_percentage: number;
  suggested_stake_fraction: number;
  model_source: ModelSource;
  lineup_confirmed: boolean | null;
  bookmaker: string | null;
}

export interface ValueBetListResponse {
  value_bets: ValueBet[];
}

export interface ValueBetFilters {
  league_id?: string;
  min_ev_threshold?: number;
  match_date?: string;
  market_type?: MarketType;
  model_source?: ModelSource;
}

export interface PipelineRunResponse {
  matches_processed: number;
  total_value_bets: number;
  value_bets_by_market_type: Record<string, number>;
  value_bets_by_model_source: Record<string, number>;
  value_bets: ValueBet[];
}

export interface SettleBetRequest {
  match_id: string;
  market_type: MarketType;
  outcome: string;
  line: number | null;
  local_odds: number;
  result: BetResult;
  settled_at: string;
  closing_sharp_odds: number | null;
}

export interface SettleBetResponse {
  value_bet: ValueBet;
  result: BetResult;
  settled_at: string;
  closing_sharp_odds: number | null;
  profit_loss: number;
  clv: number | null;
}

export interface ApiErrorBody {
  detail: string;
}
```

There is no test for a pure type-only file — TypeScript's own compiler is the check (Step 5 of this task).

- [ ] **Step 2: Write the failing client tests**

Create `frontend/src/api/client.test.ts`:

```typescript
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/server";
import { apiGet, apiPost, ApiError, NetworkError } from "./client";

const BASE_URL = "http://localhost:8000";

describe("apiGet", () => {
  it("returns the parsed JSON body on a successful response", async () => {
    server.use(http.get(`${BASE_URL}/health`, () => HttpResponse.json({ status: "ok" })));

    const result = await apiGet<{ status: string }>("/health");

    expect(result).toEqual({ status: "ok" });
  });

  it("throws ApiError with the backend's detail message on an error response", async () => {
    server.use(
      http.get(`${BASE_URL}/value-bets`, () =>
        HttpResponse.json({ detail: "no encontrado" }, { status: 404 })
      )
    );

    const error = await apiGet("/value-bets").catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(404);
    expect(error.message).toBe("no encontrado");
  });

  it("throws NetworkError when the request fails at the network level", async () => {
    server.use(http.get(`${BASE_URL}/health`, () => HttpResponse.error()));

    await expect(apiGet("/health")).rejects.toBeInstanceOf(NetworkError);
  });
});

describe("apiPost", () => {
  it("sends a JSON body and returns the parsed response", async () => {
    server.use(
      http.post(`${BASE_URL}/value-bets/settle`, async ({ request }) => {
        const body = await request.json();
        return HttpResponse.json({ received: body });
      })
    );

    const result = await apiPost<{ received: unknown }>("/value-bets/settle", {
      match_id: "m1",
    });

    expect(result).toEqual({ received: { match_id: "m1" } });
  });

  it("supports calls with no body", async () => {
    server.use(http.post(`${BASE_URL}/pipeline/run`, () => HttpResponse.json({ ok: true })));

    const result = await apiPost<{ ok: boolean }>("/pipeline/run");

    expect(result).toEqual({ ok: true });
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run (inside `frontend/`): `npm run test -- client.test.ts`
Expected: FAIL — `Failed to resolve import "./client"` (the module doesn't exist yet).

- [ ] **Step 4: Implement the client**

Create `frontend/src/api/client.ts`:

```typescript
import type { ApiErrorBody } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export class NetworkError extends Error {
  constructor(cause: unknown) {
    super("No se pudo conectar con el servidor.");
    this.name = "NetworkError";
    this.cause = cause;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
  } catch (cause) {
    throw new NetworkError(cause);
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiError(response.status, body?.detail ?? `Error ${response.status}`);
  }

  return (await response.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run (inside `frontend/`): `npm run test -- client.test.ts`
Expected: PASS — 2 test files (`App.test.tsx`, `client.test.ts`), 6 tests passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "feat(frontend): add typed API client and response types"
```

---

### Task 4: TanStack Query hooks

**Files:**
- Modify: `frontend/src/main.tsx`
- Create: `frontend/src/api/valueBets.ts`
- Create: `frontend/src/api/pipeline.ts`
- Test: `frontend/src/api/valueBets.test.tsx`
- Test: `frontend/src/api/pipeline.test.tsx`

**Interfaces:**
- Consumes: `apiGet`/`apiPost`/`ApiError`/`NetworkError` and all types from Task 3's `./client`/`./types`.
- Produces: `valueBetsQueryKey(filters: ValueBetFilters): readonly ["value-bets", ValueBetFilters]`, `useValueBets(filters: ValueBetFilters)` (TanStack Query `useQuery` result over `ValueBetListResponse`), `useSettleBet()` (TanStack Query `useMutation` result, `mutate(request: SettleBetRequest)`, resolves to `SettleBetResponse`), `useRunPipeline()` (TanStack Query `useMutation` result, `mutate()` with no args, resolves to `PipelineRunResponse`) — all three consumed directly by the components in Tasks 5-9.

- [ ] **Step 1: Wire `QueryClientProvider` in `main.tsx`**

Open `frontend/src/main.tsx`. It currently looks like:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

Change it to:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

const queryClient = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
```

There is no automated test for `main.tsx` (it's the entry point that mounts to the real DOM `#root`, not present in the jsdom test environment) — this matches how the rest of this plan tests `App` directly instead.

- [ ] **Step 2: Write the failing `useValueBets` test**

Create `frontend/src/api/valueBets.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "../test/server";
import type { ValueBet } from "./types";
import { useValueBets, useSettleBet, valueBetsQueryKey } from "./valueBets";

const BASE_URL = "http://localhost:8000";

const sampleBet: ValueBet = {
  match_id: "match-1",
  league_id: "league-1",
  market_type: "MATCH_WINNER_1X2",
  outcome: "Home",
  line: null,
  local_odds: 2.1,
  fair_probability: 0.55,
  edge_percentage: 4.2,
  suggested_stake_fraction: 0.015,
  model_source: "MARKET",
  lineup_confirmed: null,
  bookmaker: "Betplay",
};

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useValueBets", () => {
  it("fetches value bets with the filters encoded as query params", async () => {
    let capturedUrl = "";
    server.use(
      http.get(`${BASE_URL}/value-bets`, ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json({ value_bets: [sampleBet] });
      })
    );

    const { result } = renderHook(
      () => useValueBets({ league_id: "epl", min_ev_threshold: 0.02 }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.value_bets).toEqual([sampleBet]);
    expect(capturedUrl).toContain("league_id=epl");
    expect(capturedUrl).toContain("min_ev_threshold=0.02");
  });

  it("omits filter params that are not set", async () => {
    let capturedUrl = "";
    server.use(
      http.get(`${BASE_URL}/value-bets`, ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json({ value_bets: [] });
      })
    );

    const { result } = renderHook(() => useValueBets({}), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(capturedUrl).toBe(`${BASE_URL}/value-bets`);
  });
});

describe("useSettleBet", () => {
  it("posts the settle request and invalidates the value-bets query on success", async () => {
    const settleResponse = {
      value_bet: sampleBet,
      result: "WON",
      settled_at: "2026-07-06T20:00:00.000Z",
      closing_sharp_odds: null,
      profit_loss: 0.015,
      clv: null,
    };
    let capturedBody: unknown = null;
    server.use(
      http.post(`${BASE_URL}/value-bets/settle`, async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json(settleResponse);
      })
    );

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    queryClient.setQueryData(valueBetsQueryKey({}), { value_bets: [] });

    function localWrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    }

    const { result } = renderHook(() => useSettleBet(), { wrapper: localWrapper });

    result.current.mutate({
      match_id: "match-1",
      market_type: "MATCH_WINNER_1X2",
      outcome: "Home",
      line: null,
      local_odds: 2.1,
      result: "WON",
      settled_at: "2026-07-06T20:00:00.000Z",
      closing_sharp_odds: null,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(capturedBody).toMatchObject({ match_id: "match-1", result: "WON" });
    expect(queryClient.getQueryState(valueBetsQueryKey({}))?.isInvalidated).toBe(true);
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run (inside `frontend/`): `npm run test -- valueBets.test.tsx`
Expected: FAIL — `Failed to resolve import "./valueBets"`.

- [ ] **Step 4: Implement `valueBets.ts`**

Create `frontend/src/api/valueBets.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "./client";
import type {
  SettleBetRequest,
  SettleBetResponse,
  ValueBetFilters,
  ValueBetListResponse,
} from "./types";

function buildValueBetsQueryString(filters: ValueBetFilters): string {
  const params = new URLSearchParams();
  if (filters.league_id) params.set("league_id", filters.league_id);
  if (filters.min_ev_threshold !== undefined) {
    params.set("min_ev_threshold", String(filters.min_ev_threshold));
  }
  if (filters.match_date) params.set("match_date", filters.match_date);
  if (filters.market_type) params.set("market_type", filters.market_type);
  if (filters.model_source) params.set("model_source", filters.model_source);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function valueBetsQueryKey(filters: ValueBetFilters) {
  return ["value-bets", filters] as const;
}

export function useValueBets(filters: ValueBetFilters) {
  return useQuery({
    queryKey: valueBetsQueryKey(filters),
    queryFn: () =>
      apiGet<ValueBetListResponse>(`/value-bets${buildValueBetsQueryString(filters)}`),
  });
}

export function useSettleBet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: SettleBetRequest) =>
      apiPost<SettleBetResponse>("/value-bets/settle", request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["value-bets"] });
    },
  });
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run (inside `frontend/`): `npm run test -- valueBets.test.tsx`
Expected: PASS — 3 tests passed.

- [ ] **Step 6: Write the failing `useRunPipeline` test**

Create `frontend/src/api/pipeline.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "../test/server";
import { valueBetsQueryKey } from "./valueBets";
import { useRunPipeline } from "./pipeline";

const BASE_URL = "http://localhost:8000";

describe("useRunPipeline", () => {
  it("runs the pipeline and invalidates the value-bets query on success", async () => {
    const runResponse = {
      matches_processed: 3,
      total_value_bets: 2,
      value_bets_by_market_type: { MATCH_WINNER_1X2: 2 },
      value_bets_by_model_source: { MARKET: 2 },
      value_bets: [],
    };
    server.use(http.post(`${BASE_URL}/pipeline/run`, () => HttpResponse.json(runResponse)));

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    queryClient.setQueryData(valueBetsQueryKey({}), { value_bets: [] });

    function wrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    }

    const { result } = renderHook(() => useRunPipeline(), { wrapper });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(runResponse);
    expect(queryClient.getQueryState(valueBetsQueryKey({}))?.isInvalidated).toBe(true);
  });
});
```

- [ ] **Step 7: Run test to verify it fails**

Run (inside `frontend/`): `npm run test -- pipeline.test.tsx`
Expected: FAIL — `Failed to resolve import "./pipeline"`.

- [ ] **Step 8: Implement `pipeline.ts`**

Create `frontend/src/api/pipeline.ts`:

```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost } from "./client";
import type { PipelineRunResponse } from "./types";

export function useRunPipeline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<PipelineRunResponse>("/pipeline/run"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["value-bets"] });
    },
  });
}
```

- [ ] **Step 9: Run test to verify it passes**

Run (inside `frontend/`): `npm run test -- pipeline.test.tsx`
Expected: PASS — 1 test passed.

- [ ] **Step 10: Run the full frontend test suite**

Run (inside `frontend/`): `npm run test`
Expected: PASS — all test files so far (`App.test.tsx`, `client.test.ts`, `valueBets.test.tsx`, `pipeline.test.tsx`) green.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/main.tsx frontend/src/api/valueBets.ts frontend/src/api/valueBets.test.tsx frontend/src/api/pipeline.ts frontend/src/api/pipeline.test.tsx
git commit -m "feat(frontend): add TanStack Query hooks for value bets and pipeline runs"
```

---

### Task 5: `ValueBetFilters` component

**Files:**
- Create: `frontend/src/components/ValueBetFilters.tsx`
- Test: `frontend/src/components/ValueBetFilters.test.tsx`

**Interfaces:**
- Consumes: `ValueBetFilters`, `MarketType`, `ModelSource` types from `../api/types` (Task 3).
- Produces: `ValueBetFilters` component (named export), props `{ filters: ValueBetFilters; onChange: (filters: ValueBetFilters) => void }` — consumed by `App.tsx` in Task 9.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ValueBetFilters.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { ValueBetFilters as Filters } from "../api/types";
import { ValueBetFilters } from "./ValueBetFilters";

function renderControlled(initial: Filters = {}) {
  const handleChange = vi.fn();
  function Harness() {
    const [filters, setFilters] = useState<Filters>(initial);
    return (
      <ValueBetFilters
        filters={filters}
        onChange={(next) => {
          handleChange(next);
          setFilters(next);
        }}
      />
    );
  }
  render(<Harness />);
  return handleChange;
}

describe("ValueBetFilters", () => {
  it("calls onChange with the accumulated league_id as the user types", async () => {
    const handleChange = renderControlled();

    await userEvent.type(screen.getByLabelText("Liga"), "epl");

    expect(handleChange).toHaveBeenLastCalledWith({ league_id: "epl" });
  });

  it("calls onChange with a numeric min_ev_threshold as the user types", async () => {
    const handleChange = renderControlled();

    await userEvent.type(screen.getByLabelText("EV mínimo"), "0.05");

    expect(handleChange).toHaveBeenLastCalledWith({ min_ev_threshold: 0.05 });
  });

  it("calls onChange with the selected market_type", async () => {
    const handleChange = renderControlled();

    await userEvent.selectOptions(screen.getByLabelText("Mercado"), "BTTS");

    expect(handleChange).toHaveBeenLastCalledWith({ market_type: "BTTS" });
  });

  it("calls onChange with the selected model_source", async () => {
    const handleChange = renderControlled();

    await userEvent.selectOptions(screen.getByLabelText("Modelo"), "STATISTICAL");

    expect(handleChange).toHaveBeenLastCalledWith({ model_source: "STATISTICAL" });
  });

  it("clears a field back to undefined when reset to the empty option", async () => {
    const handleChange = renderControlled({ market_type: "BTTS" });

    await userEvent.selectOptions(screen.getByLabelText("Mercado"), "Todos");

    expect(handleChange).toHaveBeenLastCalledWith({ market_type: undefined });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (inside `frontend/`): `npm run test -- ValueBetFilters.test.tsx`
Expected: FAIL — `Failed to resolve import "./ValueBetFilters"`.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/ValueBetFilters.tsx`:

```tsx
import type { ChangeEvent } from "react";
import type { MarketType, ModelSource, ValueBetFilters as Filters } from "../api/types";

const MARKET_TYPES: MarketType[] = ["MATCH_WINNER_1X2", "OVER_UNDER", "BTTS", "PLAYER_PROP"];
const MODEL_SOURCES: ModelSource[] = ["MARKET", "STATISTICAL", "BOTH", "PLAYER_PROPS"];

interface ValueBetFiltersProps {
  filters: Filters;
  onChange: (filters: Filters) => void;
}

export function ValueBetFilters({ filters, onChange }: ValueBetFiltersProps) {
  function updateField<K extends keyof Filters>(field: K, value: Filters[K]) {
    onChange({ ...filters, [field]: value });
  }

  return (
    <fieldset>
      <legend>Filtros</legend>
      <label>
        Liga
        <input
          type="text"
          aria-label="Liga"
          value={filters.league_id ?? ""}
          onChange={(event: ChangeEvent<HTMLInputElement>) =>
            updateField("league_id", event.target.value === "" ? undefined : event.target.value)
          }
        />
      </label>
      <label>
        EV mínimo
        <input
          type="number"
          step="0.01"
          aria-label="EV mínimo"
          value={filters.min_ev_threshold ?? ""}
          onChange={(event: ChangeEvent<HTMLInputElement>) =>
            updateField(
              "min_ev_threshold",
              event.target.value === "" ? undefined : Number(event.target.value)
            )
          }
        />
      </label>
      <label>
        Fecha
        <input
          type="date"
          aria-label="Fecha"
          value={filters.match_date ?? ""}
          onChange={(event: ChangeEvent<HTMLInputElement>) =>
            updateField("match_date", event.target.value === "" ? undefined : event.target.value)
          }
        />
      </label>
      <label>
        Mercado
        <select
          aria-label="Mercado"
          value={filters.market_type ?? ""}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            updateField(
              "market_type",
              event.target.value === "" ? undefined : (event.target.value as MarketType)
            )
          }
        >
          <option value="">Todos</option>
          {MARKET_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </label>
      <label>
        Modelo
        <select
          aria-label="Modelo"
          value={filters.model_source ?? ""}
          onChange={(event: ChangeEvent<HTMLSelectElement>) =>
            updateField(
              "model_source",
              event.target.value === "" ? undefined : (event.target.value as ModelSource)
            )
          }
        >
          <option value="">Todos</option>
          {MODEL_SOURCES.map((source) => (
            <option key={source} value={source}>
              {source}
            </option>
          ))}
        </select>
      </label>
    </fieldset>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (inside `frontend/`): `npm run test -- ValueBetFilters.test.tsx`
Expected: PASS — 5 tests passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ValueBetFilters.tsx frontend/src/components/ValueBetFilters.test.tsx
git commit -m "feat(frontend): add ValueBetFilters component"
```

---

### Task 6: `ValueBetTable` component

**Files:**
- Create: `frontend/src/components/ValueBetTable.tsx`
- Test: `frontend/src/components/ValueBetTable.test.tsx`

**Interfaces:**
- Consumes: `ValueBet` type from `../api/types` (Task 3).
- Produces: `ValueBetTable` component (named export), props `{ valueBets: ValueBet[]; onSettle: (valueBet: ValueBet) => void }` — consumed by `App.tsx` in Task 9.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ValueBetTable.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ValueBet } from "../api/types";
import { ValueBetTable } from "./ValueBetTable";

const bet: ValueBet = {
  match_id: "match-1",
  league_id: "league-1",
  market_type: "MATCH_WINNER_1X2",
  outcome: "Home",
  line: null,
  local_odds: 2.1,
  fair_probability: 0.55,
  edge_percentage: 4.2,
  suggested_stake_fraction: 0.015,
  model_source: "MARKET",
  lineup_confirmed: null,
  bookmaker: "Betplay",
};

describe("ValueBetTable", () => {
  it("shows an empty-state message when there are no value bets", () => {
    render(<ValueBetTable valueBets={[]} onSettle={vi.fn()} />);

    expect(
      screen.getByText("No hay value bets para los filtros seleccionados.")
    ).toBeInTheDocument();
  });

  it("renders one row per value bet with its data", () => {
    render(<ValueBetTable valueBets={[bet]} onSettle={vi.fn()} />);

    expect(screen.getByText("match-1")).toBeInTheDocument();
    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("4.20%")).toBeInTheDocument();
    expect(screen.getByText("Betplay")).toBeInTheDocument();
  });

  it("calls onSettle with the row's value bet when Settle is clicked", async () => {
    const handleSettle = vi.fn();
    render(<ValueBetTable valueBets={[bet]} onSettle={handleSettle} />);

    await userEvent.click(screen.getByRole("button", { name: "Settle" }));

    expect(handleSettle).toHaveBeenCalledWith(bet);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (inside `frontend/`): `npm run test -- ValueBetTable.test.tsx`
Expected: FAIL — `Failed to resolve import "./ValueBetTable"`.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/ValueBetTable.tsx`:

```tsx
import type { ValueBet } from "../api/types";

interface ValueBetTableProps {
  valueBets: ValueBet[];
  onSettle: (valueBet: ValueBet) => void;
}

export function ValueBetTable({ valueBets, onSettle }: ValueBetTableProps) {
  if (valueBets.length === 0) {
    return <p>No hay value bets para los filtros seleccionados.</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Partido</th>
          <th>Mercado</th>
          <th>Selección</th>
          <th>Línea</th>
          <th>Cuota local</th>
          <th>Prob. justa</th>
          <th>EV %</th>
          <th>Stake sugerido</th>
          <th>Modelo</th>
          <th>Casa</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {valueBets.map((bet, index) => (
          <tr key={`${bet.match_id}-${bet.market_type}-${bet.outcome}-${bet.line}-${index}`}>
            <td>{bet.match_id}</td>
            <td>{bet.market_type}</td>
            <td>{bet.outcome}</td>
            <td>{bet.line ?? "-"}</td>
            <td>{bet.local_odds}</td>
            <td>{bet.fair_probability.toFixed(3)}</td>
            <td>{bet.edge_percentage.toFixed(2)}%</td>
            <td>{bet.suggested_stake_fraction.toFixed(4)}</td>
            <td>{bet.model_source}</td>
            <td>{bet.bookmaker ?? "-"}</td>
            <td>
              <button type="button" onClick={() => onSettle(bet)}>
                Settle
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (inside `frontend/`): `npm run test -- ValueBetTable.test.tsx`
Expected: PASS — 3 tests passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ValueBetTable.tsx frontend/src/components/ValueBetTable.test.tsx
git commit -m "feat(frontend): add ValueBetTable component"
```

---

### Task 7: `RunPipelineBar` component

**Files:**
- Create: `frontend/src/components/RunPipelineBar.tsx`
- Test: `frontend/src/components/RunPipelineBar.test.tsx`

**Interfaces:**
- Consumes: `useRunPipeline()` from `../api/pipeline` (Task 4).
- Produces: `RunPipelineBar` component (named export), no props (self-contained) — consumed by `App.tsx` in Task 9.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/RunPipelineBar.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "../test/server";
import { RunPipelineBar } from "./RunPipelineBar";

const BASE_URL = "http://localhost:8000";

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("RunPipelineBar", () => {
  it("shows the run summary after a successful pipeline run", async () => {
    server.use(
      http.post(`${BASE_URL}/pipeline/run`, () =>
        HttpResponse.json({
          matches_processed: 5,
          total_value_bets: 3,
          value_bets_by_market_type: {},
          value_bets_by_model_source: {},
          value_bets: [],
        })
      )
    );

    renderWithClient(<RunPipelineBar />);
    await userEvent.click(screen.getByRole("button", { name: "Correr Pipeline" }));

    expect(
      await screen.findByText("Partidos procesados: 5 — Value bets encontradas: 3")
    ).toBeInTheDocument();
  });

  it("shows an error banner when the pipeline run fails", async () => {
    server.use(
      http.post(`${BASE_URL}/pipeline/run`, () =>
        HttpResponse.json(
          { detail: "no se pudo conectar con el proveedor externo" },
          { status: 502 }
        )
      )
    );

    renderWithClient(<RunPipelineBar />);
    await userEvent.click(screen.getByRole("button", { name: "Correr Pipeline" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "no se pudo conectar con el proveedor externo"
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (inside `frontend/`): `npm run test -- RunPipelineBar.test.tsx`
Expected: FAIL — `Failed to resolve import "./RunPipelineBar"`.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/RunPipelineBar.tsx`:

```tsx
import { useRunPipeline } from "../api/pipeline";

export function RunPipelineBar() {
  const { mutate, data, error, isPending } = useRunPipeline();

  return (
    <section>
      <button type="button" onClick={() => mutate()} disabled={isPending}>
        {isPending ? "Corriendo..." : "Correr Pipeline"}
      </button>
      {error && <p role="alert">{error.message}</p>}
      {data && (
        <p>
          Partidos procesados: {data.matches_processed} — Value bets encontradas:{" "}
          {data.total_value_bets}
        </p>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (inside `frontend/`): `npm run test -- RunPipelineBar.test.tsx`
Expected: PASS — 2 tests passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/RunPipelineBar.tsx frontend/src/components/RunPipelineBar.test.tsx
git commit -m "feat(frontend): add RunPipelineBar component"
```

---

### Task 8: `SettleBetModal` component

**Files:**
- Create: `frontend/src/components/SettleBetModal.tsx`
- Test: `frontend/src/components/SettleBetModal.test.tsx`

**Interfaces:**
- Consumes: `useSettleBet()` from `../api/valueBets` (Task 4), `BetResult`/`ValueBet` types from `../api/types` (Task 3).
- Produces: `SettleBetModal` component (named export), props `{ valueBet: ValueBet; onClose: () => void }` — consumed by `App.tsx` in Task 9.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/SettleBetModal.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { server } from "../test/server";
import type { ValueBet } from "../api/types";
import { SettleBetModal } from "./SettleBetModal";

const BASE_URL = "http://localhost:8000";

const bet: ValueBet = {
  match_id: "match-1",
  league_id: "league-1",
  market_type: "MATCH_WINNER_1X2",
  outcome: "Home",
  line: null,
  local_odds: 2.1,
  fair_probability: 0.55,
  edge_percentage: 4.2,
  suggested_stake_fraction: 0.015,
  model_source: "MARKET",
  lineup_confirmed: null,
  bookmaker: "Betplay",
};

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("SettleBetModal", () => {
  it("submits the value bet's natural key plus the form fields", async () => {
    let capturedBody: unknown = null;
    server.use(
      http.post(`${BASE_URL}/value-bets/settle`, async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({
          value_bet: bet,
          result: "WON",
          settled_at: "2026-07-06T20:00:00.000Z",
          closing_sharp_odds: null,
          profit_loss: 0.015,
          clv: null,
        });
      })
    );

    renderWithClient(<SettleBetModal valueBet={bet} onClose={vi.fn()} />);
    await userEvent.selectOptions(screen.getByLabelText("Resultado"), "WON");
    await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    expect(await screen.findByText(/Registrado\. Profit\/loss: 0\.0150/)).toBeInTheDocument();
    expect(capturedBody).toMatchObject({
      match_id: "match-1",
      market_type: "MATCH_WINNER_1X2",
      outcome: "Home",
      local_odds: 2.1,
      result: "WON",
    });
  });

  it("shows an error banner when settling fails", async () => {
    server.use(
      http.post(`${BASE_URL}/value-bets/settle`, () =>
        HttpResponse.json({ detail: "no se encontró esa apuesta" }, { status: 404 })
      )
    );

    renderWithClient(<SettleBetModal valueBet={bet} onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("no se encontró esa apuesta");
  });

  it("calls onClose when Cancelar is clicked", async () => {
    const handleClose = vi.fn();
    renderWithClient(<SettleBetModal valueBet={bet} onClose={handleClose} />);

    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(handleClose).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (inside `frontend/`): `npm run test -- SettleBetModal.test.tsx`
Expected: FAIL — `Failed to resolve import "./SettleBetModal"`.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/SettleBetModal.tsx`:

```tsx
import { useState, type FormEvent } from "react";
import { useSettleBet } from "../api/valueBets";
import type { BetResult, ValueBet } from "../api/types";

interface SettleBetModalProps {
  valueBet: ValueBet;
  onClose: () => void;
}

function toDatetimeLocalValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}`;
}

export function SettleBetModal({ valueBet, onClose }: SettleBetModalProps) {
  const [result, setResult] = useState<BetResult>("WON");
  const [settledAt, setSettledAt] = useState(() => toDatetimeLocalValue(new Date()));
  const [closingSharpOdds, setClosingSharpOdds] = useState("");
  const { mutate, error, isPending, isSuccess, data } = useSettleBet();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutate({
      match_id: valueBet.match_id,
      market_type: valueBet.market_type,
      outcome: valueBet.outcome,
      line: valueBet.line,
      local_odds: valueBet.local_odds,
      result,
      settled_at: new Date(settledAt).toISOString(),
      closing_sharp_odds: closingSharpOdds === "" ? null : Number(closingSharpOdds),
    });
  }

  return (
    <dialog open aria-label="Settle bet">
      <form onSubmit={handleSubmit}>
        <p>
          {valueBet.match_id} — {valueBet.market_type} — {valueBet.outcome}
        </p>
        <label>
          Resultado
          <select
            aria-label="Resultado"
            value={result}
            onChange={(event) => setResult(event.target.value as BetResult)}
          >
            <option value="WON">Ganada</option>
            <option value="LOST">Perdida</option>
            <option value="PUSH">Push</option>
          </select>
        </label>
        <label>
          Fecha de settle
          <input
            type="datetime-local"
            aria-label="Fecha de settle"
            value={settledAt}
            onChange={(event) => setSettledAt(event.target.value)}
          />
        </label>
        <label>
          Cuota sharp de cierre (opcional)
          <input
            type="number"
            step="0.01"
            aria-label="Cuota sharp de cierre"
            value={closingSharpOdds}
            onChange={(event) => setClosingSharpOdds(event.target.value)}
          />
        </label>
        {error && <p role="alert">{error.message}</p>}
        {isSuccess && data && (
          <p>
            Registrado. Profit/loss: {data.profit_loss.toFixed(4)}
            {data.clv !== null ? ` — CLV: ${data.clv.toFixed(4)}` : ""}
          </p>
        )}
        <button type="submit" disabled={isPending}>
          {isPending ? "Guardando..." : "Confirmar"}
        </button>
        <button type="button" onClick={onClose}>
          Cancelar
        </button>
      </form>
    </dialog>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (inside `frontend/`): `npm run test -- SettleBetModal.test.tsx`
Expected: PASS — 3 tests passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SettleBetModal.tsx frontend/src/components/SettleBetModal.test.tsx
git commit -m "feat(frontend): add SettleBetModal component"
```

---

### Task 9: Wire `App.tsx`

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx` (replaces the Task 2 smoke test with full integration coverage)

**Interfaces:**
- Consumes: `useValueBets` (Task 4), `RunPipelineBar` (Task 7), `ValueBetFilters` (Task 5), `ValueBetTable` (Task 6), `SettleBetModal` (Task 8).
- Produces: the complete single-screen panel — no later task depends on this one.

- [ ] **Step 1: Write the failing integration tests**

Replace `frontend/src/App.test.tsx` entirely with:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "./test/server";
import App from "./App";

const BASE_URL = "http://localhost:8000";

const bet = {
  match_id: "match-1",
  league_id: "league-1",
  market_type: "MATCH_WINNER_1X2",
  outcome: "Home",
  line: null,
  local_odds: 2.1,
  fair_probability: 0.55,
  edge_percentage: 4.2,
  suggested_stake_fraction: 0.015,
  model_source: "MARKET",
  lineup_confirmed: null,
  bookmaker: "Betplay",
};

function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  );
}

describe("App", () => {
  it("renders the panel title", () => {
    server.use(http.get(`${BASE_URL}/value-bets`, () => HttpResponse.json({ value_bets: [] })));
    renderApp();

    expect(screen.getByRole("heading", { name: "Panel Operativo" })).toBeInTheDocument();
  });

  it("loads and displays value bets on mount", async () => {
    server.use(http.get(`${BASE_URL}/value-bets`, () => HttpResponse.json({ value_bets: [bet] })));

    renderApp();

    expect(await screen.findByText("Home")).toBeInTheDocument();
  });

  it("refreshes the value bets list after a successful pipeline run", async () => {
    let callCount = 0;
    server.use(
      http.get(`${BASE_URL}/value-bets`, () => {
        callCount += 1;
        return HttpResponse.json({ value_bets: callCount === 1 ? [] : [bet] });
      }),
      http.post(`${BASE_URL}/pipeline/run`, () =>
        HttpResponse.json({
          matches_processed: 1,
          total_value_bets: 1,
          value_bets_by_market_type: {},
          value_bets_by_model_source: {},
          value_bets: [bet],
        })
      )
    );

    renderApp();
    await screen.findByText("No hay value bets para los filtros seleccionados.");

    await userEvent.click(screen.getByRole("button", { name: "Correr Pipeline" }));

    expect(await screen.findByText("Home")).toBeInTheDocument();
  });

  it("opens the settle modal from a table row and closes it on cancel", async () => {
    server.use(http.get(`${BASE_URL}/value-bets`, () => HttpResponse.json({ value_bets: [bet] })));

    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "Settle" }));

    expect(screen.getByLabelText("Resultado")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByLabelText("Resultado")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (inside `frontend/`): `npm run test -- App.test.tsx`
Expected: FAIL — the "loads and displays value bets", "refreshes...", and "opens the settle modal..." tests fail because `App` doesn't render `ValueBetTable`/`RunPipelineBar`/`SettleBetModal` yet (only the title test passes, since that behavior already exists from Task 2).

- [ ] **Step 3: Implement the full `App`**

Replace `frontend/src/App.tsx` entirely with:

```tsx
import { useState } from "react";
import { useValueBets } from "./api/valueBets";
import type { ValueBet, ValueBetFilters as Filters } from "./api/types";
import { RunPipelineBar } from "./components/RunPipelineBar";
import { ValueBetFilters } from "./components/ValueBetFilters";
import { ValueBetTable } from "./components/ValueBetTable";
import { SettleBetModal } from "./components/SettleBetModal";

function App() {
  const [filters, setFilters] = useState<Filters>({});
  const [selectedBet, setSelectedBet] = useState<ValueBet | null>(null);
  const { data, error, isLoading } = useValueBets(filters);

  return (
    <main>
      <h1>Panel Operativo</h1>
      <RunPipelineBar />
      <ValueBetFilters filters={filters} onChange={setFilters} />
      {isLoading && <p>Cargando value bets...</p>}
      {error && <p role="alert">{error.message}</p>}
      {data && <ValueBetTable valueBets={data.value_bets} onSettle={setSelectedBet} />}
      {selectedBet && (
        <SettleBetModal valueBet={selectedBet} onClose={() => setSelectedBet(null)} />
      )}
    </main>
  );
}

export default App;
```

- [ ] **Step 4: Run tests to verify they pass**

Run (inside `frontend/`): `npm run test -- App.test.tsx`
Expected: PASS — 4 tests passed.

- [ ] **Step 5: Run the full frontend suite and build**

Run (inside `frontend/`):

```bash
npm run test
npm run build
```

Expected: every test file passes; `npm run build` completes with no TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat(frontend): wire the operational panel screen end to end"
```

---

### Task 10: Docs and manual verification

**Files:**
- Create: `frontend/.env.example`
- Modify: `README.md`
- Modify: `MANUAL.md` (if it references how to operate the system — add a pointer to the panel)

**Interfaces:**
- None — this task only documents what Tasks 1-9 already built.

- [ ] **Step 1: Add `frontend/.env.example`**

Create `frontend/.env.example`:

```
# Base URL of the ev-betting-engine FastAPI backend. Defaults to
# http://localhost:8000 in client.ts if this is unset.
VITE_API_BASE_URL=http://localhost:8000
```

- [ ] **Step 2: Document the panel in `README.md`**

Open `README.md`. After the "## Lanzar el pipeline manualmente" section (ends around the line `El pipeline real necesita ... no un crash.`) and before "## Ejecutar pruebas", insert:

```markdown
## Panel web (frontend)

Un panel operativo de una sola pantalla (React + Vite, en `frontend/`) para listar value bets con filtros, correr el pipeline manualmente y registrar resultados (settle) sin usar `curl`/Swagger directamente.

```bash
# Backend (una terminal) - necesita CORS_ALLOWED_ORIGINS habilitado para
# el puerto de Vite, ya viene por defecto en .env.example:
uv run uvicorn src.presentation.api.app:app --reload

# Frontend (otra terminal):
cd frontend
cp .env.example .env
npm install
npm run dev
```

Abre la URL que imprime `npm run dev` (por defecto `http://localhost:5173`). Si Vite elige otro puerto porque el 5173 está ocupado, agregalo a `CORS_ALLOWED_ORIGINS` en el `.env` del backend.

Tests del frontend: `cd frontend && npm run test`.
```

- [ ] **Step 3: Add a pointer to the panel in `MANUAL.md`**

Open `MANUAL.md`. Find this line (in section "4. Levantar el servidor"):

```markdown
Documentación interactiva (Swagger) disponible en `http://127.0.0.1:8000/docs` una vez levantado.
```

Change it to:

```markdown
Documentación interactiva (Swagger) disponible en `http://127.0.0.1:8000/docs` una vez levantado.

Alternativa a llamar la API a mano: el panel web en `frontend/` cubre listar value bets con filtros, correr el pipeline y registrar resultados desde el navegador — ver "Panel web (frontend)" en `README.md`.
```

- [ ] **Step 4: Manually verify both servers together**

Run the backend: `uv run uvicorn src.presentation.api.app:app --reload`
Run the frontend (separate terminal): `cd frontend && npm run dev`

Open the printed frontend URL in a browser. Verify:
1. The page loads showing "Panel Operativo", the filters, and the "Correr Pipeline" button with no console errors.
2. Clicking "Correr Pipeline" shows either a summary (if `.env` has real `ODDS_API_KEY`/`SPORTMONKS_API_TOKEN`) or an error banner (if using placeholder credentials) — either way, no unhandled exception or blank screen.
3. If any value bets are showing (from a prior real pipeline run persisted in the DB), clicking "Settle" opens the modal, and "Cancelar" closes it.

This is manual QA, not an automated step — report what you observed (or if credentials are placeholders and the pipeline can't be exercised for real, note that explicitly rather than claiming full verification).

- [ ] **Step 5: Commit**

```bash
git add frontend/.env.example README.md MANUAL.md
git commit -m "docs: document the frontend operational panel"
```
