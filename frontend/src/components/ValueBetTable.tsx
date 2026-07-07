import type { ValueBet } from "../api/types";

interface ValueBetTableProps {
  valueBets: ValueBet[];
  onSettle: (valueBet: ValueBet) => void;
}

export function ValueBetTable({ valueBets, onSettle }: ValueBetTableProps) {
  if (valueBets.length === 0) {
    return <p>No hay value bets para los filtros seleccionados.</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Partido</th>
          <th>Mercado</th>
          <th>Selección</th>
          <th>Línea</th>
          <th>Cuota local</th>
          <th>Prob. justa</th>
          <th>EV %</th>
          <th>Stake sugerido</th>
          <th>Modelo</th>
          <th>Casa</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {valueBets.map((bet, index) => (
          <tr key={`${bet.match_id}-${bet.market_type}-${bet.outcome}-${bet.line}-${index}`}>
            <td>{bet.match_id}</td>
            <td>{bet.market_type}</td>
            <td>{bet.outcome}</td>
            <td>{bet.line ?? "-"}</td>
            <td>{bet.local_odds}</td>
            <td>{bet.fair_probability.toFixed(3)}</td>
            <td>{bet.edge_percentage.toFixed(2)}%</td>
            <td>{bet.suggested_stake_fraction.toFixed(4)}</td>
            <td>{bet.model_source}</td>
            <td>{bet.bookmaker ?? "-"}</td>
            <td>
              <button type="button" onClick={() => onSettle(bet)}>
                Settle
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
