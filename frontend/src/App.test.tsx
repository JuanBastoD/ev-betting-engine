import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "./test/server";
import App from "./App";

const BASE_URL = "http://localhost:8000";

const bet = {
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

function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  );
}

describe("App", () => {
  it("renders the panel title", () => {
    server.use(http.get(`${BASE_URL}/value-bets`, () => HttpResponse.json({ value_bets: [] })));
    renderApp();

    expect(screen.getByRole("heading", { name: "Panel Operativo" })).toBeInTheDocument();
  });

  it("loads and displays value bets on mount", async () => {
    server.use(http.get(`${BASE_URL}/value-bets`, () => HttpResponse.json({ value_bets: [bet] })));

    renderApp();

    expect(await screen.findByText("Home")).toBeInTheDocument();
  });

  it("refreshes the value bets list after a successful pipeline run", async () => {
    let callCount = 0;
    server.use(
      http.get(`${BASE_URL}/value-bets`, () => {
        callCount += 1;
        return HttpResponse.json({ value_bets: callCount === 1 ? [] : [bet] });
      }),
      http.post(`${BASE_URL}/pipeline/run`, () =>
        HttpResponse.json({
          matches_processed: 1,
          total_value_bets: 1,
          value_bets_by_market_type: {},
          value_bets_by_model_source: {},
          value_bets: [bet],
        })
      )
    );

    renderApp();
    await screen.findByText("No hay value bets para los filtros seleccionados.");

    await userEvent.click(screen.getByRole("button", { name: "Correr Pipeline" }));

    expect(await screen.findByText("Home")).toBeInTheDocument();
  });

  it("opens the settle modal from a table row and closes it on cancel", async () => {
    server.use(http.get(`${BASE_URL}/value-bets`, () => HttpResponse.json({ value_bets: [bet] })));

    renderApp();
    await userEvent.click(await screen.findByRole("button", { name: "Settle" }));

    expect(screen.getByLabelText("Resultado")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByLabelText("Resultado")).not.toBeInTheDocument();
  });
});
