import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { server } from "../test/server";
import type { ValueBet } from "../api/types";
import { SettleBetModal } from "./SettleBetModal";

const BASE_URL = "http://localhost:8000";

const bet: ValueBet = {
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

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("SettleBetModal", () => {
  it("submits the value bet's natural key plus the form fields", async () => {
    let capturedBody: unknown = null;
    server.use(
      http.post(`${BASE_URL}/value-bets/settle`, async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({
          value_bet: bet,
          result: "WON",
          settled_at: "2026-07-06T20:00:00.000Z",
          closing_sharp_odds: null,
          profit_loss: 0.015,
          clv: null,
        });
      })
    );

    renderWithClient(<SettleBetModal valueBet={bet} onClose={vi.fn()} />);
    await userEvent.selectOptions(screen.getByLabelText("Resultado"), "WON");
    await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    expect(await screen.findByText(/Registrado\. Profit\/loss: 0\.0150/)).toBeInTheDocument();
    expect(capturedBody).toMatchObject({
      match_id: "match-1",
      market_type: "MATCH_WINNER_1X2",
      outcome: "Home",
      local_odds: 2.1,
      result: "WON",
    });
  });

  it("shows an error banner when settling fails", async () => {
    server.use(
      http.post(`${BASE_URL}/value-bets/settle`, () =>
        HttpResponse.json({ detail: "no se encontró esa apuesta" }, { status: 404 })
      )
    );

    renderWithClient(<SettleBetModal valueBet={bet} onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("no se encontró esa apuesta");
  });

  it("calls onClose when Cancelar is clicked", async () => {
    const handleClose = vi.fn();
    renderWithClient(<SettleBetModal valueBet={bet} onClose={handleClose} />);

    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(handleClose).toHaveBeenCalled();
  });
});
