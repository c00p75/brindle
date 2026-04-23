export type Role = "admin" | "operator" | "reviewer" | "viewer";

export interface UserPublic {
  id: string;
  email: string;
  role: Role;
  is_active: boolean;
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
