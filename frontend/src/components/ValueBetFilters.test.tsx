import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { ValueBetFilters as Filters } from "../api/types";
import { ValueBetFilters } from "./ValueBetFilters";

function renderControlled(initial: Filters = {}) {
  const handleChange = vi.fn();
  function Harness() {
    const [filters, setFilters] = useState<Filters>(initial);
    return (
      <ValueBetFilters
        filters={filters}
        onChange={(next) => {
          handleChange(next);
          setFilters(next);
        }}
      />
    );
  }
  render(<Harness />);
  return handleChange;
}

describe("ValueBetFilters", () => {
  it("calls onChange with the accumulated league_id as the user types", async () => {
    const handleChange = renderControlled();

    await userEvent.type(screen.getByLabelText("Liga"), "epl");

    expect(handleChange).toHaveBeenLastCalledWith({ league_id: "epl" });
  });

  it("calls onChange with a numeric min_ev_threshold as the user types", async () => {
    const handleChange = renderControlled();

    await userEvent.type(screen.getByLabelText("EV mínimo"), "0.05");

    expect(handleChange).toHaveBeenLastCalledWith({ min_ev_threshold: 0.05 });
  });

  it("calls onChange with the selected market_type", async () => {
    const handleChange = renderControlled();

    await userEvent.selectOptions(screen.getByLabelText("Mercado"), "BTTS");

    expect(handleChange).toHaveBeenLastCalledWith({ market_type: "BTTS" });
  });

  it("calls onChange with the selected model_source", async () => {
    const handleChange = renderControlled();

    await userEvent.selectOptions(screen.getByLabelText("Modelo"), "STATISTICAL");

    expect(handleChange).toHaveBeenLastCalledWith({ model_source: "STATISTICAL" });
  });

  it("clears a field back to undefined when reset to the empty option", async () => {
    const handleChange = renderControlled({ market_type: "BTTS" });

    await userEvent.selectOptions(screen.getByLabelText("Mercado"), "Todos");

    expect(handleChange).toHaveBeenLastCalledWith({ market_type: undefined });
  });
});
