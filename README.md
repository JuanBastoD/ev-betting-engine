# ev-betting-engine

Motor de detección de apuestas de **Valor Esperado Positivo (+EV)** en fútbol pre-partido. Compara cuotas "sharp" de referencia (Pinnacle) contra cuotas locales para identificar apuestas con edge positivo, incorporando datos de forma de equipo, estadísticas de jugador, lesiones y alineaciones.

Construido con **Clean Architecture** y **Domain-Driven Design**, capa por capa, cada una completamente probada (100% cobertura) antes de avanzar a la siguiente.

## Estado del proyecto

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Dominio puro: entidades, value objects, puertos (ABC), configuración | ✅ |
| 2 | Persistencia: SQLAlchemy 2.0 async, repositorios, migraciones Alembic | ✅ |
| 3 | Ingesta de cuotas sharp y forma de equipo (The Odds API) | ✅ |
| 4 | Ingesta de datos de jugador: stats, lesiones, alineaciones (Sportmonks) | ✅ |
| 5 | Scraping de casas locales con Playwright: mercados de partido y props de jugador | ✅ |
| 6 | Motor matemático de mercado: devig (4 métodos), cálculo de EV, sizing de Kelly fraccional | ✅ |
| 7 | Motor estadístico de partido: xG Dixon-Coles, ajuste por ausencias, doble confirmación con el mercado | ✅ |
| 8 | Motor estadístico de props de jugador: modelo Poisson con EWMA, ajuste por minutos y rival | ✅ |
| 9 | Orquestación: casos de uso, API FastAPI, scheduler (APScheduler), Composition Root | ✅ |
| 10+ | Calibración / modelos entrenados (ML) inyectables donde hoy están `DixonColesModel`/`PoissonPropsModel` | ⏳ pendiente |

Los tres motores cuantitativos (mercado, partido y props de jugador, todos en `src/domain/services/`) están conectados de punta a punta: `src/application/use_cases/` los invoca vía inyección de dependencias sobre los puertos del dominio, y `src/presentation/api/` expone eso como una API FastAPI con un scheduler que corre el pipeline completo periódicamente.

## Arquitectura

Cuatro capas, dependencias apuntando siempre hacia adentro:

```
presentation  →  application  →  domain  ←  infrastructure
```

- **`src/domain/`** — puro, sin dependencias de ninguna otra capa. Entidades y value objects son dataclasses inmutables (`frozen=True, slots=True`) que se validan a sí mismas en `__post_init__`. Los puertos (`src/domain/ports/`) son interfaces abstractas (ABC) que la infraestructura implementa. Tres motores cuantitativos, todos 100% deterministas y sin I/O — cuáles usa el pipeline y cuándo:
  - `src/domain/services/market_model/` — cuatro estrategias de devig (Multiplicativo, Aditivo, Shin, Power) intercambiables (patrón Strategy), cálculo de EV y sizing de Kelly fraccional, orquestados por `MarketValueDetector`. Se usa **siempre** como referencia sharp (Pinnacle) para confirmar o descartar oportunidades de los otros dos motores.
  - `src/domain/services/match_model/` — modelo de Goles Esperados (xG) Dixon-Coles a partir de la forma de los equipos, con ajuste por ausencias de jugadores clave; `MatchValueDetector` reutiliza el motor de mercado y aplica una política de doble confirmación configurable: modo **CONFIRMACIÓN** (default — solo genera value bet si mercado y modelo estadístico coinciden, `model_source=BOTH`) o **INDEPENDIENTE** (el modelo estadístico decide solo, `model_source=STATISTICAL`, sin exigir acuerdo con Pinnacle). Se usa para mercados de partido (1X2, Over/Under, BTTS).
  - `src/domain/services/player_props/` — modelo Poisson (patrón Strategy, `PoissonPropsModel`) de la probabilidad de superar una línea Over/Under en una métrica de jugador (goles, tiros a puerta, asistencias, tarjetas), a partir de una media móvil exponencial de su tasa histórica, ajustada por minutos esperados, fortaleza del rival y una penalización de confianza configurable cuando la alineación no está confirmada o el jugador está en duda/lesionado. `PlayerPropDetector` reutiliza el cálculo de EV y el Kelly fraccional del motor de mercado. Siempre `model_source=STATISTICAL` (no compara contra Pinnacle) — se usa exclusivamente para props de jugador.
- **`src/infrastructure/`**
  - `persistence/` — modelos ORM, mappers Entity↔Model, repositorios concretos (patrón Repository + Data Mapper), migraciones Alembic (async).
  - `providers/api/` — adaptadores para APIs externas (patrón Adapter + DTO Pydantic + Mapper), con reintentos y manejo de errores propios de dominio (`ProviderUnavailableError`, `RateLimitError`).
  - `providers/scraping/` — scrapers Playwright para casas locales (patrones Page Object Model + Factory + Template Method): una clase base abstracta con el flujo común (navegación con reintentos, esperas por selector, delays) y una subclase por casa (`BetplayScraper`, `StakeScraper`, `BetanoScraper`) donde viven aislados los selectores de cada sitio. Extrae mercados principales (1X2, Over/Under, BTTS) y props de jugador (goles, tiros a puerta, asistencias, tarjetas).
- **`src/application/use_cases/`** — un caso de uso por responsabilidad (Interactor), cada uno recibe sus dependencias por constructor y depende **solo** de los puertos del dominio, nunca de una implementación concreta:
  - `IngestSharpOddsUseCase` / `IngestLocalOddsUseCase` / `IngestPlayerStatsUseCase` — ingesta y persistencia (donde aplica; `TeamForm`/`InjuryStatus`/`LineupConfirmation`/`PlayerPropMarket` se obtienen frescos en cada corrida, sin repositorio propio).
  - `DetectMatchValueBetsUseCase` / `DetectPlayerPropValueBetsUseCase` — invocan `MatchValueDetector`/`PlayerPropDetector` y persisten los `ValueBet` resultantes.
  - `RunPipelineUseCase` — **Facade**: encadena los cinco anteriores para uno o varios partidos (mismo código para la corrida periódica completa y para `/value-bets/query` sobre un solo partido).
  - `ListValueBetsUseCase` — filtra `ValueBet`s persistidos (liga, EV mínimo, fecha, tipo de mercado, `model_source`) en memoria.
- **`src/presentation/api/`** — FastAPI:
  - `dependencies.py` es el **Composition Root**: el único módulo que conoce las implementaciones concretas (repositorios SQLAlchemy, `TheOddsApiClient`, `SportmonksClient`, `PlaywrightLocalOddsProvider`, y los modelos estadísticos concretos `DixonColesModel`/`PoissonPropsModel`). Los comentarios en `build_match_value_detector`/`build_player_prop_detector` marcan exactamente dónde se inyectaría un modelo entrenado (Prompt 10) sin tocar nada más.
  - `app.py` — la app y su `lifespan` (inicializa el pool de conexiones y arranca el scheduler al inicio; los detiene al final).
  - `scheduler.py` — `AsyncIOScheduler` (APScheduler) ejecuta `RunPipelineUseCase` cada `PIPELINE_INTERVAL_SECONDS`, reutilizando la misma función de wiring que usan los endpoints.
  - `exception_handlers.py` — traduce excepciones de dominio/aplicación/proveedores a códigos HTTP (`ValueError`→400, `MatchNotFoundError`/`PlayerPropNotFoundError`→404, `ProviderError`→502, cualquier otra→500), con logging estructurado (`structlog`, JSON) en cada caso.
  - `routers/` — `GET /health`, `POST /pipeline/run`, `POST /value-bets/query`, `GET /value-bets` (ver más abajo).

Ver [CLAUDE.md](CLAUDE.md) para el detalle de convenciones internas, decisiones de diseño y particularidades de cada módulo.

## API

```bash
uv run uvicorn src.presentation.api.app:app --reload
```

| Endpoint | Descripción |
|---|---|
| `GET /health` | Chequeo de salud, sin dependencias. |
| `POST /pipeline/run` | Corre el pipeline completo (ingesta sharp → ingesta local → ingesta de jugador → detección de partido → detección de props) sobre todos los partidos en `MatchRepository.list_upcoming()`. Responde el total de oportunidades encontradas, desglosado por `market_type` y por `model_source`. |
| `POST /value-bets/query` | `{"match_id": "...", "player_name": "...", "prop_type": "..."}` (los dos últimos opcionales) — corre el mismo flujo solo para ese partido/jugador y devuelve el resultado directamente en la respuesta, sin esperar al scheduler. |
| `GET /value-bets` | Lista value bets persistidos, con filtros por query string: `league_id`, `min_ev_threshold`, `match_date`, `market_type` (incluye `PLAYER_PROP`), `model_source`. Las props incluyen `lineup_confirmed`; el resto lo trae `null`. |

El pipeline periódico corre además vía APScheduler cada `PIPELINE_INTERVAL_SECONDS` (default 3600) sin necesidad de llamar a `/pipeline/run` manualmente — arranca solo con la app.

## Proveedores de datos

| Proveedor | Datos | Autenticación |
|---|---|---|
| [The Odds API](https://the-odds-api.com) | Cuotas 1X2 de Pinnacle (sharp), resultados recientes para forma de equipo | query param `apiKey` |
| [Sportmonks](https://www.sportmonks.com) | Estadísticas de jugador por partido, reportes de lesión, alineaciones confirmadas/estimadas | query param `api_token` |
| Betplay / Stake / Betano (scraping) | Cuotas locales colombianas: mercados de partido y props de jugador | n/a (Playwright headless) |

### Nota legal sobre el scraping

El scraping de casas de apuestas debe **respetar los Términos de Servicio de cada sitio** y la normativa de **Coljuegos** (regulador colombiano de juegos de suerte y azar). Este módulo está pensado para uso personal y de bajo volumen: el delay entre requests, los timeouts y los límites de reintentos son **parámetros configurables** de cada scraper (`request_delay_seconds`, `nav_timeout_ms`, `max_attempts`, ...) — configúralos de forma conservadora para no elevar la carga sobre los sitios. Verifica los ToS vigentes de cada operador antes de ejecutarlo.

## Stack técnico

- **Python 3.12+**, gestor de paquetes [uv](https://docs.astral.sh/uv/)
- **SQLAlchemy 2.0** (async) + **Alembic** (migraciones async) — SQLite/aiosqlite en desarrollo, Postgres/asyncpg en producción (solo cambia `DATABASE_URL`)
- **httpx** (cliente HTTP async) + **tenacity** (reintentos con backoff exponencial)
- **Playwright** (async, Chromium headless) para scraping de casas locales — los tests nunca abren un navegador real
- **Pydantic** / **pydantic-settings** (DTOs y configuración)
- **FastAPI** + **uvicorn** (API async) + **APScheduler** (`AsyncIOScheduler`, pipeline periódico) + **structlog** (logging estructurado en JSON)
- **pytest** + **pytest-asyncio** + **pytest-cov** + **respx** (mocking HTTP, sin red real en tests) + **hypothesis** (property-based testing para el motor matemático)

## Instalación

```bash
uv sync
cp .env.example .env
# editar .env con tus credenciales: DATABASE_URL, ODDS_API_KEY, SPORTMONKS_API_TOKEN, SPORT_KEY, ...
uv run alembic upgrade head

# Solo si vas a ejecutar el scraping real (los tests no lo necesitan):
uv run playwright install chromium
```

## Levantar el servidor

```bash
uv run uvicorn src.presentation.api.app:app --reload
```

El `lifespan` de la app inicializa el pool de conexiones a la base de datos y arranca el scheduler del pipeline al iniciar, y libera ambos al apagarse — no hace falta ningún paso manual adicional. Requiere `alembic upgrade head` ejecutado antes (el lifespan no crea tablas, solo abre el pool).

## Lanzar el pipeline manualmente

Con el servidor corriendo, sin esperar al scheduler:

```bash
curl -X POST http://127.0.0.1:8000/pipeline/run
```

O para un solo partido (opcionalmente filtrando por jugador/tipo de prop):

```bash
curl -X POST http://127.0.0.1:8000/value-bets/query \
  -H "Content-Type: application/json" \
  -d '{"match_id": "abc123", "player_name": "Carlos Bacca", "prop_type": "SHOTS_ON_TARGET"}'
```

El pipeline real necesita `playwright install chromium` (scraping local) y credenciales válidas de The Odds API / Sportmonks — sin eso, `/pipeline/run` responde `502 Bad Gateway` con el error del proveedor que falló, no un crash.

## Ejecutar pruebas

```bash
uv run pytest                    # suite completa con reporte de cobertura
uv run pytest tests/domain/      # solo un subdirectorio
uv run pytest --no-cov           # sin overhead de cobertura, iteración rápida
```

La configuración (`pyproject.toml`) trata cualquier warning como error (`filterwarnings = ["error"]`): una corrida en verde implica cero warnings, no solo cero fallos. La convención del proyecto (no forzada por config) ha sido mantener 100% de cobertura de líneas y ramas al cierre de cada fase.

## Migraciones

```bash
uv run alembic revision --autogenerate -m "descripción del cambio"
uv run alembic upgrade head
uv run alembic downgrade base   # revertir todo (usar con cuidado)
```

`alembic/env.py` lee `DATABASE_URL` a través de `src/infrastructure/config.py`, no de `alembic.ini` — cambiar de SQLite a Postgres es solo cambiar una variable de entorno.
