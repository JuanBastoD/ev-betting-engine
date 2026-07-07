import { useState, type FormEvent } from "react";
import { useSettleBet } from "../api/valueBets";
import type { BetResult, ValueBet } from "../api/types";

interface SettleBetModalProps {
  valueBet: ValueBet;
  onClose: () => void;
}

function toDatetimeLocalValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}`;
}

export function SettleBetModal({ valueBet, onClose }: SettleBetModalProps) {
  const [result, setResult] = useState<BetResult>("WON");
  const [settledAt, setSettledAt] = useState(() => toDatetimeLocalValue(new Date()));
  const [closingSharpOdds, setClosingSharpOdds] = useState("");
  const { mutate, error, isPending, isSuccess, data } = useSettleBet();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutate({
      match_id: valueBet.match_id,
      market_type: valueBet.market_type,
      outcome: valueBet.outcome,
      line: valueBet.line,
      local_odds: valueBet.local_odds,
      result,
      settled_at: new Date(settledAt).toISOString(),
      closing_sharp_odds: closingSharpOdds === "" ? null : Number(closingSharpOdds),
    });
  }

  return (
    <dialog open aria-label="Settle bet">
      <form onSubmit={handleSubmit}>
        <p>
          {valueBet.match_id} — {valueBet.market_type} — {valueBet.outcome}
        </p>
        <label>
          Resultado
          <select
            aria-label="Resultado"
            value={result}
            onChange={(event) => setResult(event.target.value as BetResult)}
          >
            <option value="WON">Ganada</option>
            <option value="LOST">Perdida</option>
            <option value="PUSH">Push</option>
          </select>
        </label>
        <label>
          Fecha de settle
          <input
            type="datetime-local"
            aria-label="Fecha de settle"
            value={settledAt}
            onChange={(event) => setSettledAt(event.target.value)}
          />
        </label>
        <label>
          Cuota sharp de cierre (opcional)
          <input
            type="number"
            step="0.01"
            aria-label="Cuota sharp de cierre"
            value={closingSharpOdds}
            onChange={(event) => setClosingSharpOdds(event.target.value)}
          />
        </label>
        {error && <p role="alert">{error.message}</p>}
        {isSuccess && data && (
          <p>
            Registrado. Profit/loss: {data.profit_loss.toFixed(4)}
            {data.clv !== null ? ` — CLV: ${data.clv.toFixed(4)}` : ""}
          </p>
        )}
        <button type="submit" disabled={isPending}>
          {isPending ? "Guardando..." : "Confirmar"}
        </button>
        <button type="button" onClick={onClose}>
          Cancelar
        </button>
      </form>
    </dialog>
  );
}
