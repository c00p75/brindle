export type Role = "admin" | "operator" | "reviewer" | "viewer";

export interface UserPublic {
  id: string;
  email: string;
  role: Role;
  is_active: boolean;
  totp_enabled: boolean;
}

export interface TOTPSetupResponse {
  secret: string;
  provisioning_uri: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserPublic;
}

export type BotState =
  | "draft"
  | "validated"
  | "ready"
  | "running"
  | "paused"
  | "halted"
  | "error"
  | "archived";

export interface Bot {
  id: string;
  name: string;
  owner_email: string;
  state: BotState;
  active_config_version: number | null;
  created_at_ms: number;
  updated_at_ms: number;
}

export interface RiskLimits {
  max_position_notional: number;
  max_total_exposure: number;
  max_daily_loss: number;
  max_drawdown_pct: number;
  max_open_orders: number;
  kill_switch: boolean;
}

export interface BrokerConfig {
  type: string;
  environment: string;
  account_id: string;
  credential_ref: string;
  symbol_namespace: string;
  app_id?: string | null;
  rate_limit_profile?: string | null;
  extra?: Record<string, unknown>;
}

export interface StrategyConfig {
  strategy_id: string;
  params: Record<string, unknown>;
}

export interface BotConfig {
  bot_id: string;
  version: number;
  name: string;
  description?: string | null;
  strategy: StrategyConfig;
  risk: RiskLimits;
  broker: BrokerConfig;
  symbols: string[];
}

export type ConfigStatus =
  | "draft"
  | "validated"
  | "pending_approval"
  | "approved"
  | "applied"
  | "superseded"
  | "rejected";

export interface ConfigVersion {
  bot_id: string;
  version: number;
  status: ConfigStatus;
  config: BotConfig;
  created_by: string;
  created_at_ms: number;
  applied_at_ms: number | null;
  approved_by: string | null;
  validation_errors: string[];
  validation_warnings: string[];
  parent_version: number | null;
}

export interface DiffEntry {
  path: string;
  before: unknown;
  after: unknown;
}

export interface AuditEvent {
  id: string;
  actor_email: string;
  actor_role: string;
  action: string;
  resource_type: string;
  resource_id: string;
  at_ms: number;
  diff: DiffEntry[];
  metadata: Record<string, unknown>;
  outcome: "ok" | "error";
  reason: string | null;
}

export interface Position {
  bot_id: string;
  symbol: string;
  quantity: number;
  avg_price: number | null;
  realized_pnl: number;
  updated_at_ms: number;
}

export interface Order {
  client_order_id: string;
  bot_id: string;
  strategy_id: string;
  config_version: number;
  adapter_id: string;
  symbol: string;
  side: "buy" | "sell";
  order_type: string;
  quantity: number;
  notional: number | null;
  limit_price: number | null;
  status: "filled" | "rejected" | "pending" | "cancelled";
  broker_order_id: string | null;
  reason: string | null;
  submitted_at_ms: number;
}

export interface Fill {
  id: string;
  bot_id: string;
  client_order_id: string;
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  fees: number;
  filled_at_ms: number;
}

export interface Contract {
  contract_id: string;
  bot_id: string;
  symbol: string;
  contract_type: "CALL" | "PUT" | string;
  stake: number;
  expected_payout: number;
  purchase_price: number;
  payout_received: number | null;
  pnl: number | null;
  status: "open" | "won" | "lost";
  purchased_at_ms: number;
  expires_at_ms: number | null;
  settled_at_ms: number | null;
}

export interface ContractsSummary {
  open_count: number;
  won_count: number;
  lost_count: number;
  total_count: number;
  total_staked: number;
  total_payout: number;
  realized_pnl: number;
  win_rate: number;
  // echoed back by the backend so the UI can label cards with the window
  since_ms: number | null;
  until_ms: number | null;
}

export interface BrokerBalance {
  available: number | null;
  total: number | null;
  currency: string | null;
  ts_ms: number | null;
  source: "runtime_cache" | "live_fetch" | "no_config" | "fetch_error" | "empty";
  error?: string;
  // First balance ever observed for this bot. Used to compute net change
  // without hardcoding any account-size assumption. Null if not yet snapshotted.
  starting_balance: number | null;
  starting_balance_currency: string | null;
  starting_balance_at_ms: number | null;
}

export interface BacktestRequest {
  strategy_id: string;
  params: Record<string, unknown>;
  symbols: string[];
  bars: number;
  seed: string;
  risk: Record<string, unknown>;
  save: boolean;
}

export interface BacktestMetrics {
  run_id: string;
  strategy_id: string;
  symbols: string[];
  bars_simulated: number;
  total_orders: number;
  filled_orders: number;
  rejected_orders: number;
  total_realized_pnl: number;
  win_trades: number;
  loss_trades: number;
  win_rate: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  completed_at_ms: number;
}

export type TickSignalStatus =
  | "warming_up"
  | "watching"
  | "cooldown"
  | "signal_buy"
  | "signal_sell"
  | "weak_signal";

export interface TickSignal {
  status: TickSignalStatus;
  label: string;
  detail: string;
  cooldown_remaining: number;
}

export interface TickEvent {
  symbol: string;
  ts_ms: number;
  mark_price: number;
  strategy_id: string;
  position_qty: number;
  bars_available: number;
  bars_needed: number;
  indicators: Record<string, number>;
  signal: TickSignal;
}

export type Severity = "info" | "warning" | "critical";
export type AlertStatus = "active" | "acknowledged" | "resolved";

export interface Alert {
  id: string;
  severity: Severity;
  status: AlertStatus;
  source: string;
  message: string;
  bot_id: string | null;
  created_at_ms: number;
  acknowledged_by: string | null;
  acknowledged_at_ms: number | null;
  metadata: Record<string, unknown>;
}
export interface BalanceSnapshot {
  id: string;
  bot_id: string;
  balance: number;
  currency: string;
  at_ms: number;
  source: string;
}

export interface AnalyticsBucket {
  bucket_ms: number;
  // contract activity in this bucket
  pnl: number;
  staked: number;
  payout: number;
  won: number;
  lost: number;
  open: number;
  total: number;
  win_rate: number;
  // balance bookends — null when no balance snapshot landed in this bucket
  balance_open: number | null;
  balance_close: number | null;
  balance_low: number | null;
  balance_high: number | null;
}
