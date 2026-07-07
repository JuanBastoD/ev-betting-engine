import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "../test/server";
import { RunPipelineBar } from "./RunPipelineBar";

const BASE_URL = "http://localhost:8000";

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("RunPipelineBar", () => {
  it("shows the run summary after a successful pipeline run", async () => {
    server.use(
      http.post(`${BASE_URL}/pipeline/run`, () =>
        HttpResponse.json({
          matches_processed: 5,
          total_value_bets: 3,
          value_bets_by_market_type: {},
          value_bets_by_model_source: {},
          value_bets: [],
        })
      )
    );

    renderWithClient(<RunPipelineBar />);
    await userEvent.click(screen.getByRole("button", { name: "Correr Pipeline" }));

    expect(
      await screen.findByText("Partidos procesados: 5 — Value bets encontradas: 3")
    ).toBeInTheDocument();
  });

  it("shows an error banner when the pipeline run fails", async () => {
    server.use(
      http.post(`${BASE_URL}/pipeline/run`, () =>
        HttpResponse.json(
          { detail: "no se pudo conectar con el proveedor externo" },
          { status: 502 }
        )
      )
    );

    renderWithClient(<RunPipelineBar />);
    await userEvent.click(screen.getByRole("button", { name: "Correr Pipeline" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "no se pudo conectar con el proveedor externo"
    );
  });
});
