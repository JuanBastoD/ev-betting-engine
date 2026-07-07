import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ValueBet } from "../api/types";
import { ValueBetTable } from "./ValueBetTable";

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

describe("ValueBetTable", () => {
  it("shows an empty-state message when there are no value bets", () => {
    render(<ValueBetTable valueBets={[]} onSettle={vi.fn()} />);

    expect(
      screen.getByText("No hay value bets para los filtros seleccionados.")
    ).toBeInTheDocument();
  });

  it("renders one row per value bet with its data", () => {
    render(<ValueBetTable valueBets={[bet]} onSettle={vi.fn()} />);

    expect(screen.getByText("match-1")).toBeInTheDocument();
    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("4.20%")).toBeInTheDocument();
    expect(screen.getByText("Betplay")).toBeInTheDocument();
  });

  it("calls onSettle with the row's value bet when Settle is clicked", async () => {
    const handleSettle = vi.fn();
    render(<ValueBetTable valueBets={[bet]} onSettle={handleSettle} />);

    await userEvent.click(screen.getByRole("button", { name: "Settle" }));

    expect(handleSettle).toHaveBeenCalledWith(bet);
  });
});
