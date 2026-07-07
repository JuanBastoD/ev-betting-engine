import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost } from "./client";
import type { PipelineRunResponse } from "./types";

export function useRunPipeline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<PipelineRunResponse>("/pipeline/run"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["value-bets"] });
    },
  });
}
