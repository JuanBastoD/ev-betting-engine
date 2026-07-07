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
