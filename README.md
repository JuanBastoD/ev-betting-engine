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
| 8+ | Casos de uso de aplicación conectando ambos motores a datos reales, capa de presentación | ⏳ pendiente |

`src/application/` y `src/presentation/` existen como esqueleto pero aún no tienen lógica: los dos motores cuantitativos (mercado en `src/domain/services/market_model/`, estadístico en `src/domain/services/match_model/`) ya calculan probabilidad justa, edge y stake sugerido, pero todavía no hay un caso de uso que los conecte a los proveedores de datos reales, ni una API/CLI expuesta.

## Arquitectura

Cuatro capas, dependencias apuntando siempre hacia adentro:

```
presentation  →  application  →  domain  ←  infrastructure
```

- **`src/domain/`** — puro, sin dependencias de ninguna otra capa. Entidades y value objects son dataclasses inmutables (`frozen=True, slots=True`) que se validan a sí mismas en `__post_init__`. Los puertos (`src/domain/ports/`) son interfaces abstractas (ABC) que la infraestructura implementa. Dos motores cuantitativos, ambos 100% deterministas y sin I/O:
  - `src/domain/services/market_model/` — cuatro estrategias de devig (Multiplicativo, Aditivo, Shin, Power) intercambiables (patrón Strategy), cálculo de EV y sizing de Kelly fraccional, orquestados por `MarketValueDetector`.
  - `src/domain/services/match_model/` — modelo de Goles Esperados (xG) Dixon-Coles a partir de la forma de los equipos, con ajuste por ausencias de jugadores clave; `MatchValueDetector` reutiliza el motor de mercado y aplica una política de doble confirmación configurable (mercado + modelo estadístico, o modelo estadístico solo).
- **`src/infrastructure/`**
  - `persistence/` — modelos ORM, mappers Entity↔Model, repositorios concretos (patrón Repository + Data Mapper), migraciones Alembic (async).
  - `providers/api/` — adaptadores para APIs externas (patrón Adapter + DTO Pydantic + Mapper), con reintentos y manejo de errores propios de dominio (`ProviderUnavailableError`, `RateLimitError`).
  - `providers/scraping/` — scrapers Playwright para casas locales (patrones Page Object Model + Factory + Template Method): una clase base abstracta con el flujo común (navegación con reintentos, esperas por selector, delays) y una subclase por casa (`BetplayScraper`, `StakeScraper`, `BetanoScraper`) donde viven aislados los selectores de cada sitio. Extrae mercados principales (1X2, Over/Under, BTTS) y props de jugador (goles, tiros a puerta, asistencias, tarjetas).
- **`src/application/`** — casos de uso (aún no implementados).
- **`src/presentation/`** — API/CLI (aún no implementada).

Ver [CLAUDE.md](CLAUDE.md) para el detalle de convenciones internas, decisiones de diseño y particularidades de cada módulo.

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
- **pytest** + **pytest-asyncio** + **pytest-cov** + **respx** (mocking HTTP, sin red real en tests) + **hypothesis** (property-based testing para el motor matemático)

## Instalación

```bash
uv sync
cp .env.example .env
# editar .env con tus credenciales: DATABASE_URL, ODDS_API_KEY, SPORTMONKS_API_TOKEN
uv run alembic upgrade head

# Solo si vas a ejecutar el scraping real (los tests no lo necesitan):
uv run playwright install chromium
```

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
