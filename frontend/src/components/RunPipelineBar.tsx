import { useRunPipeline } from "../api/pipeline";

export function RunPipelineBar() {
  const { mutate, data, error, isPending } = useRunPipeline();

  return (
    <section>
      <button type="button" onClick={() => mutate()} disabled={isPending}>
        {isPending ? "Corriendo..." : "Correr Pipeline"}
      </button>
      {error && <p role="alert">{error.message}</p>}
      {data && (
        <p>
          Partidos procesados: {data.matches_processed} — Value bets encontradas:{" "}
          {data.total_value_bets}
        </p>
      )}
    </section>
  );
}
