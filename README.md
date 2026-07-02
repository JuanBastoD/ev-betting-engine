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
| 5+ | Casos de uso de aplicación, cálculo de EV, capa de presentación | ⏳ pendiente |

`src/application/` y `src/presentation/` existen como esqueleto pero aún no tienen lógica: todavía no hay cálculo de probabilidad justa, de edge, ni una API/CLI expuesta.

## Arquitectura

Cuatro capas, dependencias apuntando siempre hacia adentro:

```
presentation  →  application  →  domain  ←  infrastructure
```

- **`src/domain/`** — puro, sin dependencias de ninguna otra capa. Entidades y value objects son dataclasses inmutables (`frozen=True, slots=True`) que se validan a sí mismas en `__post_init__`. Los puertos (`src/domain/ports/`) son interfaces abstractas (ABC) que la infraestructura implementa.
- **`src/infrastructure/`**
  - `persistence/` — modelos ORM, mappers Entity↔Model, repositorios concretos (patrón Repository + Data Mapper), migraciones Alembic (async).
  - `providers/api/` — adaptadores para APIs externas (patrón Adapter + DTO Pydantic + Mapper), con reintentos y manejo de errores propios de dominio (`ProviderUnavailableError`, `RateLimitError`).
- **`src/application/`** — casos de uso (aún no implementados).
- **`src/presentation/`** — API/CLI (aún no implementada).

Ver [CLAUDE.md](CLAUDE.md) para el detalle de convenciones internas, decisiones de diseño y particularidades de cada módulo.

## Proveedores de datos

| Proveedor | Datos | Autenticación |
|---|---|---|
| [The Odds API](https://the-odds-api.com) | Cuotas 1X2 de Pinnacle (sharp), resultados recientes para forma de equipo | query param `apiKey` |
| [Sportmonks](https://www.sportmonks.com) | Estadísticas de jugador por partido, reportes de lesión, alineaciones confirmadas/estimadas | query param `api_token` |

## Stack técnico

- **Python 3.12+**, gestor de paquetes [uv](https://docs.astral.sh/uv/)
- **SQLAlchemy 2.0** (async) + **Alembic** (migraciones async) — SQLite/aiosqlite en desarrollo, Postgres/asyncpg en producción (solo cambia `DATABASE_URL`)
- **httpx** (cliente HTTP async) + **tenacity** (reintentos con backoff exponencial)
- **Pydantic** / **pydantic-settings** (DTOs y configuración)
- **pytest** + **pytest-asyncio** + **pytest-cov** + **respx** (mocking HTTP, sin red real en tests)

## Instalación

```bash
uv sync
cp .env.example .env
# editar .env con tus credenciales: DATABASE_URL, ODDS_API_KEY, SPORTMONKS_API_TOKEN
uv run alembic upgrade head
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
