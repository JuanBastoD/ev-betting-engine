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
