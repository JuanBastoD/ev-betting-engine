# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`ev-betting-engine`: a pre-match +EV (positive expected value) detection engine for football betting. It ingests "sharp" reference odds (Pinnacle via The Odds API) and team/player statistics (Sportmonks), and will eventually compare local bookmaker odds against a fair-probability model to surface positive-EV bets. Built strictly as Clean Architecture / DDD, one numbered "Prompt" (phase) at a time, each phase fully tested and committed before the next begins.

**Current state**: domain model (including both quantitative cores: market-model devig/EV/Kelly, and match-model Dixon-Coles xG), persistence layer, both API data-ingestion adapters, and the local-bookmaker scraping adapter (Playwright) are done. `src/application/` and `src/presentation/` are still empty stubs - no use cases wiring either model to real data yet, no API or CLI.

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
- `ports/`: ABCs only, no implementation. Two flavors: repositories (`MatchRepository`, `OddsRepository`, `ValueBetRepository`, `PlayerRepository`, `PlayerStatsRepository`) and external-data providers (`SharpOddsProvider`, `LocalOddsProvider`, `StatsProvider`, `PlayerStatsProvider`). `LocalOddsProvider` covers both the main match markets (`get_odds`) and player props (`get_player_props`).
- `PlayerPropMarket` deliberately carries a full `match: Match` reference (the lesson from the `OddsQuote` gap below) but a `player_name: str` instead of a `Player` entity: bookmakers expose only a display label, and resolving it to a known `Player` is application-layer matching, not ingestion. There is no repository port / ORM model / migration for `PlayerPropMarket` yet - persisting props needs its own decision when a use case wants to store them.

`OddsQuote` carries a full `match: Match` reference (fixed at the start of Phase 6 - it originally didn't, and `SqlAlchemyOddsRepository.save()` used to work around that with an optional `match_id` kwarg; that workaround is gone, `save()` now matches `OddsRepository`'s declared signature exactly and upserts the quote's own match). `ValueBet` gained a required `model_source: ModelSource` (`MARKET` / `STATISTICAL` / `BOTH` / `PLAYER_PROPS`) - which probability model (or combination) produced it - ahead of `MarketValueDetector`. `MATCH_STATS` was renamed to `STATISTICAL` and `BOTH` was added in Phase 7, before either had ever been produced by any code - a safe rename, not a breaking one.

Known, deliberately-flagged (not fixed) gap: `ValueBet` carries no bookmaker reference (only `local_odds`, a bare number) - the same class of gap `OddsQuote` used to have. Not in scope for Phase 6's market-model work; flag rather than fix if it becomes a blocker.

### Domain services (`src/domain/services/market_model/`)

The quantitative core comparing sharp (Pinnacle) odds against local bookmaker odds for match markets (1X2/Over-Under/BTTS). Pure domain service: no I/O, fully deterministic, no infrastructure imports (not even `scipy`/`numpy` - the two non-closed-form devig methods below use a 100-fixed-iteration bisection helper in `_bisection.py` instead).

- `devig.py`: Strategy pattern, one `DevigStrategy.devig(odds) -> list[Probability]` per overround-removal method - `MultiplicativeDevig`, `AdditiveDevig`, `ShinDevig`, `PowerDevig`. All four agree exactly in two hand-verifiable cases used throughout the tests: **no-vig** (raw implied probabilities already sum to 1.0 - every method is a no-op) and **symmetric-with-vig** (identical odds on every outcome - the fair split must be 1/n by symmetry, regardless of method). `MultiplicativeDevig`/`ShinDevig`/`PowerDevig` are mathematically guaranteed to always produce valid probabilities; `AdditiveDevig` is not - subtracting an equal *absolute* share of the overround can push a longshot's raw probability negative in a heavily skewed market (a known, documented weakness of the method, not a bug), which surfaces as a `ValueError` from `Probability`'s own invariant. This exact failure mode was found by the hypothesis property test before being pinned as a concrete example in `test_devig.py`.
- `ev_calculator.py`: `calculate_ev` is deliberately independent of `devig.py` - it only needs a `Probability`, from wherever it came, so the future team-form/player-prop statistical engines can call it directly. `exceeds_ev_threshold` takes `min_ev_threshold` as a plain float parameter (matching `Settings.min_ev_threshold`) rather than reading `Settings` itself, keeping the domain import-free.
- `kelly.py`: `kelly_stake` is generic (probability/odds/fraction/cap only) so it's reusable beyond the market model. `Stake.amount` here is a **fraction of bankroll** (e.g. 0.025 = 2.5%), not a currency amount - converting to a concrete stake size needs the user's actual bankroll, an application-layer concern for a later phase. `Stake`'s own invariant forbids `amount <= 0`, so "no bet" (Kelly's f* <= 0, or `kelly_fraction`/`max_fraction` configured to 0) returns `None` rather than `Stake(0.0)`.
- `detector.py`: `MarketValueDetector.detect(sharp_quotes, local_quotes)` orchestrates devig -> EV -> Kelly -> `ValueBet(model_source=ModelSource.MARKET)`. Takes a `DevigStrategy` instance by constructor injection. `sharp_quotes` must be every outcome of one match+market from one sharp bookmaker; every `local_quote` must belong to that same match+market and to an outcome the sharp side actually quoted, or `detect()` raises - mixing markets/matches is treated as a caller bug, not something to silently drop or skip. `fair_probabilities(sharp_quotes)` (devig-and-map, validated) and `require_same_market(...)` are public **so `MatchValueDetector` (Phase 7) can reuse them instead of re-deriving devig-orchestration logic** - `detect()` itself is just those two building blocks plus the EV/Kelly loop.

### Domain services (`src/domain/services/match_model/`)

The match-statistics quantitative core: derives its **own** opinion on 1X2/Over-Under/BTTS from team-form goal data (Dixon-Coles xG), independent of Pinnacle. Pure domain service, same purity/determinism bar as `market_model`.

- `team_strength.py`: `calculate_team_strength(form, league_average_goals, recent_form=None, recent_form_weight=0.6)` turns a `TeamForm` into attack/defense ratios relative to the league average. `TeamForm` (Phase 3) is an aggregate over up to 10 matches with **no per-match dates or venue split** - it cannot itself support "weight recent matches more" or "split home vs away performance". Both requirements are pushed to this function's *boundary* instead of into `TeamForm`: home/away split is just calling this function once with a home-only `TeamForm` and once with an away-only one (the caller slices by venue, this module doesn't know how); recency weighting is an *optional* second, shorter-window `TeamForm` (`recent_form`) blended in via `recent_form_weight` - omitting it still works, using the single `form` window alone.
- `absence_adjustment.py`: `apply_absence_adjustment` reduces a team's attack strength for key (forward/midfielder by default) players who are INJURED/SUSPENDED (full, configurable `reduction_per_key_absence`) or DOUBTFUL (discounted by `doubtful_weight`, and sets `has_unconfirmed_absences=True` on the result - mirrors the Phase 4 `estimate_start_probability` fallback pattern). "Key" also requires the player's goals+assists across supplied `PlayerMatchStats` to clear `min_goal_involvements`. Only touches attack (a missing striker/creative midfielder reduces goal output); defense is left untouched, a deliberately narrower scope. Propagating `has_unconfirmed_absences` into a persisted `ValueBet` is an application-layer decision beyond this domain service - there's no field on `ValueBet` for it, same "flag, don't fix" posture as the `ValueBet`-has-no-bookmaker gap above.
- `xg_model.py`: Strategy pattern (`MatchStatisticalModel.predict_match_probabilities`), current implementation `DixonColesModel` - bivariate Poisson with the Dixon & Coles (1997) tau correction for low-scoring dependence (0-0/1-0/0-1/1-1). Builds the full scoreline grid (truncated at `max_goals`, default 10, renormalized to sum to 1.0 exactly) and derives 1X2/Over-Under (configurable lines, default 1.5/2.5/3.5)/BTTS from it. Two hypothesis-found correctness issues, both fixed and pinned as regression tests: (1) individual grid cells clamped to `>= 0.0` before summing - the tau correction's `1 + lambda*rho` term goes negative once `lambda*abs(rho)` exceeds 1, reachable by multiplying together individually-reasonable attack/defense/home_advantage/league_average_goals inputs even though the resulting lambda (~10+) is unrealistic for football; (2) aggregate probabilities (`home_win`/`btts_yes`/etc.) clamped to `[0.0, 1.0]` since summing ~100 grid cells can overshoot by a sub-epsilon float rounding amount.
- `match_value_detector.py`: `MatchValueDetector` reuses `MarketValueDetector.fair_probabilities`/`require_same_market` for the market side and `calculate_ev`/`exceeds_ev_threshold`/`kelly_stake` for pricing - it adds only the statistical prediction and the `ConfirmationMode` policy. `CONFIRMATION` (default): a `ValueBet` (`model_source=BOTH`) is only emitted when market EV *and* statistical EV both individually clear `min_ev_threshold` against the same local odds, priced off their `market_weight`-blended probability. `INDEPENDENT`: statistical EV alone decides (`model_source=STATISTICAL`), `sharp_quotes` isn't required at all. The blend is never rechecked against the threshold after combining - EV is linear in probability, so a weighted blend of two probabilities that individually clear the bar mathematically must clear it too.

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

### Infrastructure - scraping (`src/infrastructure/providers/scraping/`)

Playwright-based adapter for local Colombian bookmakers (Betplay, Stake, Betano), implementing `LocalOddsProvider`. Patterns: Page Object Model + Factory + Template Method.

- `base.py`: `AbstractBookmakerScraper` owns the whole shared flow (rate-limit delay -> `goto` + `wait_for_selector` with tenacity retries -> `inner_html` -> parse). Playwright touches exactly three page operations (`goto`, `wait_for_selector`, `inner_html`/`click`) so tests fake the Page trivially. Retry/backoff/delay/timeouts are constructor args (same reasoning as the API clients). 1X2 parsing is position-based (first=Home, second=Draw, third=Away), not name-based - sites abbreviate team names unpredictably.
- One module per bookmaker (`betplay.py`, `stake.py`, `betano.py`): all of a site's CSS selectors, label vocabulary (Spanish/English, over/under prefixes, prop-type names) and URL scheme live in its class only. Each registers itself with `@ScraperFactory.register`; `scraping/__init__.py` imports all scrapers so importing the package wires the registry - a new bookmaker is one new subclass + one import line, no orchestrator changes.
- **Parsing is 100% pure**: scrapers grab container `inner_html` and hand the string to `parse_match_odds`/`parse_player_props`, which run on `html_utils.py` - a tiny stdlib-only (html.parser) fragment parser written to avoid adding beautifulsoup/selectolax as a dependency. This is what lets the whole parse layer be tested against local `.html` fixtures with `page=None`.
- Unrecognized market/prop labels are *skipped*, not errors (sites offer far more markets than the domain models); missing structural blocks raise `SelectorNotFoundError`, malformed odds text raises `OddsParsingError`. All scraping exceptions extend `ScrapingError`, which extends the shared `ProviderError` - no Playwright exception may leak past this package.
- `browser.py`: `PlaywrightBrowserSession` is the only place that launches Chromium (headless, realistic user-agent/viewport); its `close()` releases context/browser/driver even if a step fails. `provider.py`: `PlaywrightLocalOddsProvider` is scoped to one bookmaker per instance (mirroring the sharp provider's one-sport_key scoping), opens a fresh Page per call and always closes it.
- Real scraping needs `uv run playwright install chromium` once; **tests never launch a browser** and don't need it. README carries the ToS/Coljuegos legal note - keep delays conservative and configurable.

### Testing conventions

- HTTP is always mocked with `respx` (`with respx.mock(assert_all_called=True) as router: ...`), never real network - respx's default `assert_all_mocked=True` makes an accidental real call fail loudly.
- Persistence tests use an in-memory SQLite engine with `poolclass=StaticPool` (required - without it, each connection checkout would see its own empty `:memory:` database) and a session bound to a connection-level transaction that's rolled back at teardown for isolation, even though repositories only flush.
- Retry-related client tests construct the client with near-zero `wait_min`/`wait_max`/`wait_multiplier` so exhausting retries doesn't add real seconds to the suite.
- Fixtures for external APIs live in `fixtures/*.json` next to their tests and are meant to be realistic sample payloads, not minimal stubs - reuse and extend them rather than inlining ad hoc dicts when adding coverage for the same endpoint.
- Scraping tests never launch a browser or touch the network: Playwright's `Page` and the `async_playwright()` stack are replaced by hand-rolled fakes in `tests/infrastructure/providers/scraping/fakes.py` (failure queues let a test script "fail twice, then succeed" to exercise retries without real waits). The `.html` fixtures for the three bookmakers encode the *same* logical odds content in each site's own markup/language/decimal format, so `test_scrapers_parsing.py` parametrizes one expected result across all scrapers - keep that equivalence when extending them.
- Hypothesis (`@given`) is used throughout both `services/market_model` and `services/match_model` for invariant tests (probabilities sum to 1, stay in [0,1], stakes never negative). It flags function-scoped pytest fixtures used under `@given` as a health-check failure (not reset between generated examples) - for entities that are immutable/side-effect-free to construct (a `Team`, a `Match`), build them as plain module-level constants instead of fixtures in those specific test functions, per `tests/domain/services/match_model/test_xg_model.py`/`test_absence_adjustment.py`.
- Both quantitative-core test suites hand-derive expected values independently of the implementation (exact fractions for devig, direct transcriptions of the Dixon-Coles formula for xG) rather than re-running the source under test - see the module docstrings in `test_devig.py`/`test_xg_model.py` for the derivations. Several hypothesis-found edge cases in both modules were fixed and pinned as concrete regression tests rather than only living in the property test that found them.
