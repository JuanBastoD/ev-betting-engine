# Manual de uso — ev-betting-engine

Este documento explica **qué hace el programa** y **cómo operarlo día a día**. Para el detalle técnico de arquitectura, patrones y convenciones de código, ver [CLAUDE.md](CLAUDE.md); para la referencia rápida de instalación/comandos, ver [README.md](README.md). Este manual es el intermedio: pensado para usarlo, no para modificarlo.

## Índice

1. [Qué es y qué problema resuelve](#1-qué-es-y-qué-problema-resuelve)
2. [Cómo razona el sistema (los tres motores)](#2-cómo-razona-el-sistema-los-tres-motores)
3. [Instalación y configuración](#3-instalación-y-configuración)
4. [Levantar el servidor](#4-levantar-el-servidor)
5. [Uso diario: correr el pipeline](#5-uso-diario-correr-el-pipeline)
6. [Leer una value bet](#6-leer-una-value-bet)
7. [Ciclo de calibración (Nivel 1)](#7-ciclo-de-calibración-nivel-1)
8. [Referencia de endpoints](#8-referencia-de-endpoints)
9. [Configuración (.env) explicada](#9-configuración-env-explicada)
10. [Límites conocidos y notas legales](#10-límites-conocidos-y-notas-legales)

---

## 1. Qué es y qué problema resuelve

`ev-betting-engine` busca **apuestas con Valor Esperado Positivo (+EV)** en fútbol, antes de que arranque el partido (pre-match). La idea central:

- Una casa de apuestas "sharp" (de referencia, en este caso **Pinnacle** vía The Odds API) fija cuotas muy eficientes — su margen de error es bajísimo porque mueve mucho volumen y ajusta rápido.
- Las casas locales colombianas (Betplay, Stake, Betano) a veces ofrecen una cuota **más generosa** que la que Pinnacle implica como "justa", por lentitud en ajustar, promociones, o simplemente errores de pricing.
- El programa **compara ambas** y, cuando encuentra una diferencia a favor del apostador, calcula:
  - la **probabilidad justa** del resultado (quitándole el margen/vigorish a la cuota de Pinnacle),
  - el **edge** (cuánto EV tiene la apuesta),
  - el **stake sugerido** (usando Kelly fraccional, para no apostar de más).

Además de comparar contra Pinnacle, el sistema tiene **dos motores estadísticos propios** (independientes de Pinnacle) que generan su propia opinión sobre la probabilidad de un resultado, a partir de datos de forma de equipo y estadísticas de jugador — así no depende 100% de que Pinnacle esté "bien".

**Lo que el programa NO hace**: no coloca apuestas por vos. Es un motor de **detección**, no de ejecución. La decisión de apostar y el manejo del dinero real quedan del lado humano.

## 2. Cómo razona el sistema (los tres motores)

Todo vive en `src/domain/services/`. Los tres son independientes entre sí y pueden coexistir en un mismo partido:

### a) Motor de mercado (`market_model`)
Compara Pinnacle vs. la casa local en mercados de partido (1X2, Over/Under, BTTS). Le quita el margen a las cuotas de Pinnacle (hay 4 métodos matemáticos distintos para hacerlo, configurable) para obtener la probabilidad "justa", y la compara contra la cuota local.

### b) Motor estadístico de partido (`match_model`)
Genera su **propia** predicción de 1X2/Over-Under/BTTS a partir de la forma reciente de los dos equipos (modelo Dixon-Coles de goles esperados — xG), ajustando por lesiones/suspensiones de jugadores clave. Tiene dos modos:
- **CONFIRMACIÓN** (default): solo marca una value bet si el mercado (Pinnacle) *y* el modelo estadístico están de acuerdo en que hay edge. Más conservador.
- **INDEPENDIENTE**: decide solo con su propio modelo, sin pedirle acuerdo a Pinnacle. Más agresivo, y útil si Pinnacle no cubre bien esa liga.

### c) Motor de props de jugador (`player_props`)
Para líneas Over/Under de un jugador (goles, tiros a puerta, asistencias, tarjetas), modela la métrica como una distribución de Poisson a partir de su tasa histórica reciente (con más peso a los partidos recientes), ajustada por minutos esperados (según si está confirmado en la alineación) y la fortaleza del rival. Si el jugador está en duda/lesionado, o su titularidad no está confirmada, el sistema **penaliza la confianza** de esa proyección automáticamente.

Los tres motores alimentan la misma salida: una **`ValueBet`**, con el mismo formato sin importar de cuál motor haya salido (ver [sección 6](#6-leer-una-value-bet)).

## 3. Instalación y configuración

```bash
uv sync
cp .env.example .env
```

Editá `.env` con tus credenciales reales:

| Variable | Qué es | Dónde conseguirla |
|---|---|---|
| `DATABASE_URL` | Cadena de conexión (SQLite para desarrollo, Postgres para producción) | — |
| `ODDS_API_KEY` | API key de The Odds API (cuotas Pinnacle) | https://the-odds-api.com |
| `SPORTMONKS_API_TOKEN` | Token de Sportmonks (stats de jugador, lesiones, alineaciones) | https://www.sportmonks.com |
| `SPORT_KEY` | Qué liga rastrea esta instancia (ej. `soccer_epl`) | catálogo de sport keys de The Odds API |
| `LOCAL_BOOKMAKER` | Qué casa local scrapear: `Betplay`, `Stake` o `Betano` | — |

Después, creá las tablas en la base de datos (una sola vez, y cada vez que haya una migración nueva):

```bash
uv run alembic upgrade head
```

Si vas a correr el scraping real contra las casas locales (no hace falta para los tests):

```bash
uv run playwright install chromium
```

## 4. Levantar el servidor

```bash
uv run uvicorn src.presentation.api.app:app --reload
```

Al arrancar, la app:
1. Abre el pool de conexiones a la base de datos.
2. Arranca un scheduler interno que corre el pipeline completo cada `PIPELINE_INTERVAL_SECONDS` (default: 3600s = 1 hora) **automáticamente**, sin que tengas que llamar a ningún endpoint.

Documentación interactiva (Swagger) disponible en `http://127.0.0.1:8000/docs` una vez levantado.

Alternativa a llamar la API a mano: el panel web en `frontend/` cubre listar value bets con filtros, correr el pipeline y registrar resultados desde el navegador — ver "Panel web (frontend)" en `README.md`.

## 5. Uso diario: correr el pipeline

El pipeline hace, en orden, para cada partido: ingesta de cuotas Pinnacle → ingesta de cuotas locales (scraping) → ingesta de datos de jugador → detección de value bets de partido → detección de value bets de props. El resultado son cero o más `ValueBet` persistidas en la base de datos.

**No hace falta llamarlo a mano** — el scheduler ya lo corre solo. Pero podés forzarlo:

```bash
# Sobre todos los partidos próximos que conoce el sistema
curl -X POST http://127.0.0.1:8000/pipeline/run

# Sobre un solo partido puntual (más rápido para probar)
curl -X POST http://127.0.0.1:8000/value-bets/query \
  -H "Content-Type: application/json" \
  -d '{"match_id": "abc123"}'

# Filtrando además por jugador/tipo de prop
curl -X POST http://127.0.0.1:8000/value-bets/query \
  -H "Content-Type: application/json" \
  -d '{"match_id": "abc123", "player_name": "Carlos Bacca", "prop_type": "SHOTS_ON_TARGET"}'
```

Si `/pipeline/run` responde `502 Bad Gateway`, es porque falló un proveedor externo (The Odds API, Sportmonks, o el scraping — por ejemplo si falta `playwright install chromium`), no un bug del sistema.

Para ver qué encontró, sin volver a correr nada:

```bash
curl http://127.0.0.1:8000/value-bets
```

Con filtros opcionales por query string: `league_id`, `min_ev_threshold` (ej. `0.03` = 3% mínimo), `match_date` (`YYYY-MM-DD`), `market_type` (`MATCH_WINNER_1X2`, `OVER_UNDER`, `BTTS`, `PLAYER_PROP`), `model_source` (`MARKET`, `STATISTICAL`, `BOTH`).

## 6. Leer una value bet

Cada `ValueBet` que devuelve la API tiene esta forma:

```json
{
  "match_id": "abc123",
  "league_id": "epl",
  "market_type": "MATCH_WINNER_1X2",
  "outcome": "Home",
  "line": null,
  "local_odds": 2.30,
  "fair_probability": 0.4789,
  "edge_percentage": 10.15,
  "suggested_stake_fraction": 0.018,
  "model_source": "MARKET",
  "lineup_confirmed": null,
  "bookmaker": "Betplay"
}
```

Cómo leerlo:

- **`outcome`**: qué resultado, en texto ("Home", "Draw", "Away", "Over", "Under", o para props algo como `"Lionel Messi SHOTS_ON_TARGET Over"`).
- **`local_odds`**: la cuota que ofrece la casa local (`bookmaker`) para ese resultado.
- **`fair_probability`**: la probabilidad que el sistema considera "justa" (después de quitar el margen de Pinnacle, o según el modelo estadístico).
- **`edge_percentage`**: el EV en porcentaje. `10.15` significa que, en promedio y a largo plazo, esa apuesta rinde ~10.15% del monto apostado. Solo aparecen bets con edge positivo (todo lo demás se descarta).
- **`suggested_stake_fraction`**: **fracción del bankroll** a apostar (Kelly fraccional, no Kelly completo — más conservador). `0.018` = 1.8% del bankroll total, **no** un monto en pesos. Vos multiplicás por tu bankroll real.
- **`model_source`**: de qué motor salió — `MARKET` (solo comparación con Pinnacle), `STATISTICAL` (solo el modelo propio, en props siempre es así), `BOTH` (mercado y modelo estadístico coincidieron).
- **`lineup_confirmed`**: solo tiene valor (`true`/`false`) en props de jugador — indica si la titularidad estaba confirmada oficialmente o era una estimación. `null` en el resto de mercados.
- **`bookmaker`**: la casa local donde se detectó esa cuota (puede ser `null` en bets antiguas de antes de que este campo existiera).

## 7. Ciclo de calibración (Nivel 1)

Detectar value bets es solo la mitad del trabajo — hay que verificar **si el sistema realmente acierta** con la frecuencia que dice acertar. Para eso existe el flujo de calibración: cuando un partido termina y sabés el resultado real, lo "resolvés" (settle), y el sistema acumula esos resultados para medir qué tan bien calibrado está.

### Paso 1 — Resolver una apuesta (`settle`)

Cuando ya sabés si la apuesta ganó, perdió, o fue push (anulada/reembolsada):

```bash
curl -X POST http://127.0.0.1:8000/value-bets/settle \
  -H "Content-Type: application/json" \
  -d '{
        "match_id": "abc123",
        "market_type": "MATCH_WINNER_1X2",
        "outcome": "Home",
        "line": null,
        "local_odds": 2.30,
        "result": "WON",
        "settled_at": "2026-08-16T22:00:00Z",
        "closing_sharp_odds": 2.05
      }'
```

- `result`: `"WON"`, `"LOST"` o `"PUSH"`.
- `closing_sharp_odds` (opcional): la cuota de Pinnacle justo antes del inicio del partido — sirve para calcular el **CLV** (Closing Line Value): si el mercado se movió a tu favor después de que apostaste, es una señal de que tenías una edge real, independientemente de si esa apuesta puntual ganó o perdió.
- La búsqueda del `ValueBet` a resolver es por **clave natural**: mismo partido + mismo `outcome`/`line` + misma `local_odds` exacta que se detectó. Si no hay una coincidencia exacta, responde `404`.

La respuesta trae `profit_loss` (en la misma unidad que `suggested_stake_fraction`, fracción de bankroll) y `clv` ya calculados.

### Paso 2 — Consultar el reporte de calibración

Con suficientes apuestas resueltas acumuladas:

```bash
curl http://127.0.0.1:8000/calibration/report
```

Devuelve, global y segmentado por tipo de mercado / casa / motor / tipo de prop:

- **Brier score** y **log loss**: qué tan bien calibradas están las probabilidades que predice el sistema (más bajo = mejor). `null` si no hay apuestas resueltas todavía en ese segmento.
- **Curva de calibración**: 10 buckets (0-10%, 10-20%, ..., por default) comparando la probabilidad promedio que predijo el sistema en ese rango contra la frecuencia real observada de aciertos. Si un bucket dice "predicho 35%, observado 22%" — el sistema está **sobreestimando** sistemáticamente esa franja.
- **CLV promedio**: si en promedio el mercado se mueve a favor después de apostar (señal de que las cuotas locales sí estaban mal fijadas).

Filtrable: `?model_source=STATISTICAL`, `?market_type=PLAYER_PROP`, o ambos combinados.

### Paso 3 — Recalcular factores de corrección

Si la curva de calibración muestra un sesgo sistemático en algún segmento (ej. "las props de tiros a puerta las sobreestimo un 8%"), podés generar un **factor de corrección** explícito y auditable:

```bash
curl -X POST http://127.0.0.1:8000/calibration/factors/recompute
```

Esto calcula, para cada segmento con al menos `CALIBRATION_MIN_SAMPLE_SIZE` apuestas resueltas (default: 30 — configurable, ver sección 9), un factor = frecuencia observada / probabilidad promedio predicha. Un factor de `0.92` significa "multiplicá la probabilidad predicha por 0.92 antes de calcular el EV" para corregir esa sobreestimación.

Cada corrida **agrega una versión nueva** — nunca sobreescribe la anterior, así queda un historial auditable de cómo fue cambiando la corrección con el tiempo. Los factores quedan calculados y persistidos, pero **hoy el pipeline todavía no los aplica automáticamente** — aplicarlos antes de `calculate_ev` en el flujo de detección es la extensión natural una vez que haya suficiente historial para confiar en ellos.

## 8. Referencia de endpoints

| Método | Ruta | Para qué sirve |
|---|---|---|
| `GET` | `/health` | Chequeo de salud, sin dependencias externas. |
| `POST` | `/pipeline/run` | Corre el pipeline completo sobre todos los partidos próximos conocidos. |
| `POST` | `/value-bets/query` | Corre el pipeline solo para un partido puntual (`match_id`), con filtros opcionales por jugador/tipo de prop. |
| `GET` | `/value-bets` | Lista las value bets ya detectadas y persistidas, con filtros. |
| `POST` | `/value-bets/settle` | Marca una value bet como resuelta (ganó/perdió/push) con el resultado real. |
| `GET` | `/calibration/report` | Métricas de calibración (Brier, log loss, curva, CLV), global y segmentado. |
| `POST` | `/calibration/factors/recompute` | Recalcula y persiste una nueva versión de los factores de corrección por segmento. |

## 9. Configuración (`.env`) explicada

| Variable | Default | Qué controla |
|---|---|---|
| `KELLY_FRACTION` | `0.5` | Qué fracción del Kelly completo usar al sugerir stake (0.5 = medio Kelly, más conservador). |
| `MIN_EV_THRESHOLD` | `0.02` | Edge mínimo (2%) para que algo se considere value bet. Subilo si querés menos falsos positivos, bajalo para ver más oportunidades marginales. |
| `MATCH_CONFIRMATION_MODE` | `CONFIRMATION` | `CONFIRMATION` (mercado y modelo estadístico deben coincidir) vs `INDEPENDENT` (el modelo estadístico decide solo). |
| `MARKET_WEIGHT` | `0.5` | En modo `CONFIRMATION`, cuánto peso tiene la probabilidad del mercado vs. la del modelo estadístico al mezclarlas. |
| `LEAGUE_AVERAGE_GOALS` | `1.35` | Goles promedio por equipo por partido en la liga rastreada — normaliza el modelo de xG. Ajustalo por liga (ligas ofensivas más alto, defensivas más bajo). |
| `PIPELINE_INTERVAL_SECONDS` | `3600` | Cada cuánto corre el pipeline automáticamente. |
| `CALIBRATION_BUCKET_WIDTH` | `0.1` | Ancho de cada bucket de la curva de calibración (0.1 = 10 buckets). |
| `CALIBRATION_MIN_SAMPLE_SIZE` | `30` | Mínimo de apuestas resueltas por segmento antes de calcular un factor de corrección para él. |

## 10. Límites conocidos y notas legales

- **El scraping de casas locales debe respetar los Términos de Servicio de cada sitio y la normativa de Coljuegos** (regulador colombiano). Pensado para uso personal, bajo volumen — los delays/timeouts/reintentos son configurables y conviene dejarlos conservadores.
- Los factores de corrección (sección 7, paso 3) se calculan y guardan, pero **todavía no se aplican automáticamente** en el pipeline de detección — es un paso manual/futuro.
- No existe (todavía, ver README para el criterio de activación) un modelo entrenado con Machine Learning — los tres motores son modelos estadísticos clásicos (devig, Dixon-Coles, Poisson), no un modelo que "aprende" de los resultados. La calibración de este manual es justamente el paso previo indispensable antes de considerar eso.
- El sistema **no ejecuta apuestas reales** ni gestiona dinero — solo detecta y reporta oportunidades.
