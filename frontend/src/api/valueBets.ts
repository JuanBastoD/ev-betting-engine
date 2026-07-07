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
