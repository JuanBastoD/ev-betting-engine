# Frontend operational panel — design

**Date**: 2026-07-06
**Status**: approved for planning

## Purpose

`ev-betting-engine` is currently API-only (FastAPI + Swagger, no UI). This
adds a small React SPA — a single-screen operational panel — so the solo
operator can browse detected value bets, trigger the pipeline on demand, and
record real-world bet outcomes (settle) without hitting the API directly via
Swagger/curl.

Out of scope for this design (deferred, not forgotten):
- Calibration report screen (`GET /calibration/report`) and correction-factor
  recompute (`POST /calibration/factors/recompute`) — not selected for v1.
- Multi-page navigation / React Router — only one screen exists in v1; adding
  the calibration report later is the natural trigger to introduce routing.
- Authentication — local-only usage for now, single operator.
- Visual/CSS polish via Stitch — this design covers architecture and data
  flow only; Stitch-generated mockups are applied during implementation.

## Architecture

New `frontend/` directory at the repo root, a standalone Vite + React +
TypeScript project. It talks to the existing FastAPI backend purely over
HTTP — no shared code, no monorepo tooling (npm workspaces, etc.) beyond two
sibling folders in the same git repo.

```
BETTING/
  src/                          # backend, existing
    presentation/api/
      app.py                     # + CORSMiddleware
      config.py                  # + Settings.cors_allowed_origins
  frontend/                     # new
    src/
      api/
        client.ts                 # typed fetch wrapper, base URL from env
        valueBets.ts               # TanStack Query hooks: useValueBets, useSettleBet
        pipeline.ts                # TanStack Query mutation: useRunPipeline
        types.ts                   # TS types mirroring FastAPI schemas
      components/
        ValueBetTable.tsx
        ValueBetFilters.tsx
        SettleBetModal.tsx
        RunPipelineBar.tsx
      App.tsx                    # single-screen layout
      main.tsx
    .env.example                # VITE_API_BASE_URL=http://localhost:8000
    vite.config.ts
    package.json
```

**Backend change (minimal)**: add `CORSMiddleware` in `create_app()`
(`app.py`), origins read from a new `Settings.cors_allowed_origins: list[str]`
env var (comma-separated, default `http://localhost:5173` — Vite's dev
port). This is the only backend change; all three endpoints the panel needs
already exist and are unchanged.

**Why no router yet**: the three v1 features (list+filter, run pipeline,
settle) all fit one screen — settle is a per-row modal, pipeline-run is a
global action that refreshes the list. Adding React Router now would be
speculative; it's a small, well-contained addition whenever a second screen
(e.g. calibration report) is built.

## Data flow / state management

TanStack Query (React Query) owns all server state — no Redux/global client
state store. Rationale: almost everything on this screen either *is* server
data or a direct action against the server; TanStack Query already handles
caching, loading/error states, and refetch-on-invalidate, which is most of
what a hand-rolled `useState`/`useEffect` version would have to reimplement.

- `useValueBets(filters)` → `GET /value-bets?league_id=...&...` — `filters`
  object is the query key, so changing any filter control triggers exactly
  one refetch with no manual wiring.
- `useRunPipeline()` → `POST /pipeline/run` mutation. `onSuccess` invalidates
  the `value-bets` query so the table refreshes with newly detected bets,
  and stores the `PipelineRunResponse` summary (matches processed, totals by
  market/model) in local component state to render inline until the next run.
- `useSettleBet()` → `POST /value-bets/settle` mutation, called from
  `SettleBetModal`. `onSuccess` closes the modal and invalidates `value-bets`.

`types.ts` mirrors `ValueBetSchema` / `SettleBetRequest` / `SettleBetResponse`
/ `PipelineRunResponse` field-for-field — no client-side reshaping or
additional computed fields; the API already returns exactly what the UI
displays.

## Screen and components

Single page, three vertical blocks:

1. **`RunPipelineBar`** — "Correr Pipeline" button (`useRunPipeline`).
   Disabled + spinner while in flight (a real run does live scraping, so it
   can take seconds). On success, shows the summary inline and triggers the
   value-bets list to refresh itself (via query invalidation, not a manual
   prop callback).

2. **`ValueBetFilters`** — the five filters `GET /value-bets` already
   supports: `league_id`, `min_ev_threshold`, `match_date`, `market_type`,
   `model_source`. Each control writes into the `filters` object that is
   `useValueBets`'s query key.

3. **`ValueBetTable`** — one row per `ValueBetSchema`: match/league, market
   type, outcome, line, local odds, fair probability, edge %, suggested
   stake fraction, model source, bookmaker. Each row has a **Settle** button
   opening `SettleBetModal` for that row.

**`SettleBetModal`** — pre-fills `match_id` / `market_type` / `outcome` /
`line` / `local_odds` read-only from the row (these are exactly the natural
key `SettleBetUseCase` looks up by, so what's shown must match what's sent
byte-for-byte). Editable fields: `result` (WON/LOST/PUSH dropdown),
`settled_at` (datetime input, default now), `closing_sharp_odds` (optional
number). Submits `SettleBetRequest`; on success closes and shows the
resulting profit/loss and CLV from `SettleBetResponse` as a toast.

## Error handling

`client.ts` distinguishes network failure (fetch rejects) from an HTTP error
response, surfacing both through TanStack Query's own `isError`/`error`
state — each of the three blocks renders its own inline error banner rather
than failing silently or crashing the page. Messages map to what the backend
already returns: 400 (domain `ValueError` — invariant/business-rule
violation) shown as-is, 404 (`ValueBetNotFoundError` on settle) shown as "no
se encontró esa apuesta con esos datos", 502 (`ProviderError` — upstream
odds/stats/scrape failure) shown as "no se pudo conectar con el proveedor
externo, reintentá más tarde". No client-side re-validation of business
rules (odds > 1.0, etc.) — the domain already enforces these; the client
only surfaces whatever message comes back.

## Testing

Vitest + React Testing Library (Vite's standard pairing) for
component/hook-level tests, with MSW (Mock Service Worker) intercepting
fetch calls at the HTTP boundary — the same principle as the backend's
`respx` convention (mock the boundary, not the function). Coverage is
behavior-focused, not the 100% line+branch bar the backend enforces, since
this layer has no domain logic, only UI glue:

- Changing a filter control produces the expected query params.
- `SettleBetModal` submits the exact payload built from the row + form
  fields.
- Error states (network failure, 400/404/502 responses) render the expected
  banner/message.
- `RunPipelineBar` shows the summary after a successful run and invalidates
  the value-bets query.

No end-to-end/browser tests in v1 (out of scope — could reuse the project's
existing Playwright familiarity later if this grows).

## API key setup (operational, not part of this design)

Handled separately as a step-by-step outside this spec — obtaining and
wiring real `ODDS_API_KEY` / `SPORTMONKS_API_TOKEN` values into `.env`
(currently placeholders) is unrelated to the frontend architecture.
