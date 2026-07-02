# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`ev-betting-engine`: a pre-match +EV (positive expected value) detection engine for football betting. It ingests "sharp" reference odds (Pinnacle via The Odds API) and team/player statistics (Sportmonks), and will eventually compare local bookmaker odds against a fair-probability model to surface positive-EV bets. Built strictly as Clean Architecture / DDD, one numbered "Prompt" (phase) at a time, each phase fully tested and committed before the next begins.

**Current state**: domain model, persistence layer, and both external data-ingestion adapters are done. `src/application/` and `src/presentation/` are still empty stubs - no use cases, no fair-probability/EV calculation, no API or CLI yet.

## Commands

```bash
# Install/sync dependencies
uv sync

# Run the full test suite (coverage is always on via pyproject addopts)
uv run pytest

# Run one file / one test
uv run pytest tests/domain/entities/test_match.py
uv run pytest tests/domain/entities/test_match.py::test_match_requires_different_teams

# Run without coverage overhead (faster iteration)
uv run pytest tests/infrastructure/providers/api/ --no-cov

# Alembic migrations (async; env.py reads DATABASE_URL through Settings, not alembic.ini)
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
uv run alembic downgrade base
```

There is no configured linter/formatter/type-checker (no ruff/mypy/black in `pyproject.toml`) - don't assume one and don't add one unasked.

`pyproject.toml` sets `filterwarnings = ["error"]`, so any warning fails the suite - a passing `uv run pytest` means zero warnings, not just zero failures. The project convention (not a configured gate) has been 100% line+branch coverage at the end of every phase; check the `tests coverage` table `uv run pytest` prints and close any gap before considering work done.

`.env` (gitignored) needs `DATABASE_URL`, `ODDS_API_KEY`, `SPORTMONKS_API_TOKEN` at minimum - see `.env.example` for the full list and defaults.

## Architecture

Four layers under `src/`, dependencies point strictly inward: `presentation -> application -> domain <- infrastructure`. **`src/domain/` never imports from any other layer** - this is checked manually at the end of every phase (walk every module, grep domain for infra/application/presentation imports) rather than enforced by tooling.

### Domain (`src/domain/`)

- `entities/`: frozen, slotted dataclasses (`@dataclass(frozen=True, slots=True)`), validated in `__post_init__`, raising `ValueError`. Entity identity is by id where one naturally exists (`Match.id`, `Team.id`); some entities nest full related entities rather than bare ids (e.g. `PlayerMatchStats.match: Match`, not `match_id: str`) so a provider adapter can build one from a single API response without a second lookup.
- `value_objects/`: same frozen/slotted/validated pattern for primitives (`DecimalOdds` > 1.0, `Probability` in [0,1], `EdgePercentage` >= -100, `Stake` > 0).
- `ports/`: ABCs only, no implementation. Two flavors: repositories (`MatchRepository`, `OddsRepository`, `ValueBetRepository`, `PlayerRepository`, `PlayerStatsRepository`) and external-data providers (`SharpOddsProvider`, `LocalOddsProvider` (unimplemented), `StatsProvider`, `PlayerStatsProvider`).

Known intentional gap: `OddsQuote` carries no match reference (only bookmaker/selection/odds/timestamp) - this was flagged rather than fixed, since fixing it means changing the domain and that wasn't in scope when discovered. `SqlAlchemyOddsRepository.save()` works around it with an optional `match_id` kwarg beyond what `OddsRepository.save()` declares. Don't "fix" this quietly; it needs an explicit decision (add a match reference to `OddsQuote`/`Selection`) if it ever gets addressed.

### Infrastructure - persistence (`src/infrastructure/persistence/`)

- `models.py`: every SQLAlchemy `DeclarativeBase` model in one file, deliberately kept separate from domain dataclasses. Includes `UTCDateTime`, a `TypeDecorator` that normalizes to UTC on both read and write - required because SQLite/aiosqlite silently drops tzinfo, which would otherwise violate the domain's tz-aware invariant on timestamps.
- `mappers.py`: explicit, pure `entity_to_model` / `entity_from_model` functions - the only file allowed to import both `src.domain` and `models.py`.
- `upserts.py`: shared get-or-create/update helpers (`upsert_team`, `upsert_league`, `upsert_bookmaker`, `upsert_match`, `upsert_player`) for reference entities that have no dedicated repository port but are nested inside ones that do (e.g. saving a `Match` transitively upserts its two `Team`s and `League`).
- `repositories/`: one file per port, e.g. `SqlAlchemyMatchRepository(MatchRepository)`. **Repositories only `flush()`, never `commit()`/`rollback()`** - the session is the unit of work, and whoever owns the session (a future use case) owns the transaction boundary.
- `session.py`: `get_session()` is the injectable async-generator dependency; the engine/sessionmaker are lazily created once from `Settings()` and cached at module level (`reset_session_factory()` for tests/shutdown).
- Alembic (`alembic/`) is async-mode, `env.py` imports `Base.metadata` as `target_metadata` and reads the DB URL through `src.infrastructure.config.Settings` (env vars/`.env`) instead of duplicating it in `alembic.ini` - switching SQLite to Postgres is only ever a `DATABASE_URL` change. `env.py` also has a `render_item` hook so the custom `UTCDateTime` type renders as plain `sa.DateTime(timezone=True)` in generated migrations (otherwise autogenerate emits an unimported reference to the application class).

### Infrastructure - external providers (`src/infrastructure/providers/`)

Two independent provider integrations, each following the same **Adapter + DTO + Mapper** shape and both under `src/infrastructure/providers/api/`:

1. **`api/`** (top-level files) - The Odds API (`TheOddsApiClient`, sharp/team-level odds and scores). Auth via `apiKey` query param.
2. **`api/player_stats/`** - Sportmonks (`SportmonksClient`, player-level stats/injuries/lineups). Auth via `api_token` query param; every response is wrapped in a `data` envelope that must be unwrapped before DTO validation.

Each integration has this internal shape - look at the sibling module before adding a third provider:
- `dtos.py`: pydantic models mirroring the raw JSON, `extra="ignore"` everywhere. Nothing outside the provider's own directory is allowed to see these.
- `client.py`: wraps `httpx.AsyncClient` (configurable timeout/pooling, async context manager). Retries via `tenacity.AsyncRetrying` **scoped to HTTP 429/5xx only** - other httpx errors, non-429 4xx, and pydantic `ValidationError`s on the response all become `ProviderUnavailableError` immediately (no retry); 429 becomes `RateLimitError` (carrying `Retry-After` when present) once retries are exhausted. Both exceptions live in `providers/exceptions.py`, shared across every provider so no `httpx`/`pydantic` exception ever leaks past this layer. Wait/attempt parameters are constructor args (not baked into a decorator) specifically so tests can pass near-zero backoff instead of sleeping for real.
- `mappers.py`: pure `dto_to_entity` functions, no I/O.
- The concrete provider class (e.g. `TheOddsApiSharpOddsProvider`, `SportmonksPlayerStatsProvider`) implements the matching domain port and is the only place that calls both `client.py` and `mappers.py`.

The two clients are standalone (no shared base class) by deliberate choice, to avoid touching the already-shipped/tested odds client when Sportmonks was added - revisit if a third provider makes the duplication worth factoring out.

Every provider adapter carries enough context in its own DTOs to build a full `Match` (home/away team names+ids, league, kickoff) from a single response, rather than requiring a separate lookup - this was a deliberate correction after the `OddsQuote` gap above was noticed.

`httpx.AsyncClient(base_url=...)` + a request path starting with `/` silently drops any path segment in `base_url` (e.g. the `/v4` in `https://api.the-odds-api.com/v4`), per RFC 3986 URL-join rules. Both clients normalize `base_url` to end with `/` and build request paths *without* a leading `/` to avoid this - keep that convention if you touch either client.

### Testing conventions

- HTTP is always mocked with `respx` (`with respx.mock(assert_all_called=True) as router: ...`), never real network - respx's default `assert_all_mocked=True` makes an accidental real call fail loudly.
- Persistence tests use an in-memory SQLite engine with `poolclass=StaticPool` (required - without it, each connection checkout would see its own empty `:memory:` database) and a session bound to a connection-level transaction that's rolled back at teardown for isolation, even though repositories only flush.
- Retry-related client tests construct the client with near-zero `wait_min`/`wait_max`/`wait_multiplier` so exhausting retries doesn't add real seconds to the suite.
- Fixtures for external APIs live in `fixtures/*.json` next to their tests and are meant to be realistic sample payloads, not minimal stubs - reuse and extend them rather than inlining ad hoc dicts when adding coverage for the same endpoint.
