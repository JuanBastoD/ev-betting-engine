import { useState } from "react";
import { useValueBets } from "./api/valueBets";
import type { ValueBet, ValueBetFilters as Filters } from "./api/types";
import { RunPipelineBar } from "./components/RunPipelineBar";
import { ValueBetFilters } from "./components/ValueBetFilters";
import { ValueBetTable } from "./components/ValueBetTable";
import { SettleBetModal } from "./components/SettleBetModal";

function App() {
  const [filters, setFilters] = useState<Filters>({});
  const [selectedBet, setSelectedBet] = useState<ValueBet | null>(null);
  const { data, error, isLoading } = useValueBets(filters);

  return (
    <main>
      <h1>Panel Operativo</h1>
      <RunPipelineBar />
      <ValueBetFilters filters={filters} onChange={setFilters} />
      {isLoading && <p>Cargando value bets...</p>}
      {error && <p role="alert">{error.message}</p>}
      {data && <ValueBetTable valueBets={data.value_bets} onSettle={setSelectedBet} />}
      {selectedBet && (
        <SettleBetModal valueBet={selectedBet} onClose={() => setSelectedBet(null)} />
      )}
    </main>
  );
}

export default App;
