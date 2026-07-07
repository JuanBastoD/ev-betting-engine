export type MarketType = "MATCH_WINNER_1X2" | "OVER_UNDER" | "BTTS" | "PLAYER_PROP";

export type ModelSource = "MARKET" | "STATISTICAL" | "BOTH" | "PLAYER_PROPS";

export type BetResult = "WON" | "LOST" | "PUSH";

export interface ValueBet {
  match_id: string;
  league_id: string;
  market_type: MarketType;
  outcome: string;
  line: number | null;
  local_odds: number;
  fair_probability: number;
  edge_percentage: number;
  suggested_stake_fraction: number;
  model_source: ModelSource;
  lineup_confirmed: boolean | null;
  bookmaker: string | null;
}

export interface ValueBetListResponse {
  value_bets: ValueBet[];
}

export interface ValueBetFilters {
  league_id?: string;
  min_ev_threshold?: number;
  match_date?: string;
  market_type?: MarketType;
  model_source?: ModelSource;
}

export interface PipelineRunResponse {
  matches_processed: number;
  total_value_bets: number;
  value_bets_by_market_type: Record<string, number>;
  value_bets_by_model_source: Record<string, number>;
  value_bets: ValueBet[];
}

export interface SettleBetRequest {
  match_id: string;
  market_type: MarketType;
  outcome: string;
  line: number | null;
  local_odds: number;
  result: BetResult;
  settled_at: string;
  closing_sharp_odds: number | null;
}

export interface SettleBetResponse {
  value_bet: ValueBet;
  result: BetResult;
  settled_at: string;
  closing_sharp_odds: number | null;
  profit_loss: number;
  clv: number | null;
}

export interface ApiErrorBody {
  detail: string;
}
