import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "../test/server";
import { valueBetsQueryKey } from "./valueBets";
import { useRunPipeline } from "./pipeline";

const BASE_URL = "http://localhost:8000";

describe("useRunPipeline", () => {
  it("runs the pipeline and invalidates the value-bets query on success", async () => {
    const runResponse = {
      matches_processed: 3,
      total_value_bets: 2,
      value_bets_by_market_type: { MATCH_WINNER_1X2: 2 },
      value_bets_by_model_source: { MARKET: 2 },
      value_bets: [],
    };
    server.use(http.post(`${BASE_URL}/pipeline/run`, () => HttpResponse.json(runResponse)));

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    queryClient.setQueryData(valueBetsQueryKey({}), { value_bets: [] });

    function wrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    }

    const { result } = renderHook(() => useRunPipeline(), { wrapper });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(runResponse);
    expect(queryClient.getQueryState(valueBetsQueryKey({}))?.isInvalidated).toBe(true);
  });
});
