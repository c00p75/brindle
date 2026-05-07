"use client";

import type {
  Alert,
  AnalyticsBucket,
  AuditEvent,
  BacktestMetrics,
  BacktestRequest,
  BalanceSnapshot,
  Bot,
  BotConfig,
  ConfigVersion,
  BrokerBalance,
  Contract,
  ContractsSummary,
  DiffEntry,
  Fill,
  Order,
  Position,
  TOTPSetupResponse,
  TokenResponse,
  UserPublic,
} from "./types";

const TOKEN_KEY = "tb.token";
const USER_KEY = "tb.user";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getUser(): UserPublic | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_KEY);
  return raw ? (JSON.parse(raw) as UserPublic) : null;
}

export function setSession(token: string, user: UserPublic): void {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init.headers as Record<string, string>) ?? {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(path, { ...init, headers });

  if (res.status === 401) {
    clearSession();
    if (typeof window !== "undefined" && !path.endsWith("/auth/login")) {
      window.location.href = "/login";
    }
  }
  if (!res.ok) {
    const body = await res.text();
    let detail = body;
    try { detail = JSON.parse(body).detail ?? body; } catch { /* text already */ }
    throw new ApiError(res.status, detail || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  login(email: string, password: string, totp_code?: string): Promise<TokenResponse> {
    return request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password, ...(totp_code ? { totp_code } : {}) }),
    });
  },
  me(): Promise<UserPublic> {
    return request("/api/auth/me");
  },
  listBots(): Promise<Bot[]> {
    return request("/api/bots");
  },
  getBot(id: string): Promise<Bot> {
    return request(`/api/bots/${id}`);
  },
  createBot(name: string): Promise<Bot> {
    return request("/api/bots", { method: "POST", body: JSON.stringify({ name }) });
  },
  startBot(id: string): Promise<Bot> {
    return request(`/api/bots/${id}/start`, { method: "POST" });
  },
  pauseBot(id: string): Promise<Bot> {
    return request(`/api/bots/${id}/pause`, { method: "POST" });
  },
  stopBot(id: string): Promise<Bot> {
    return request(`/api/bots/${id}/stop`, { method: "POST" });
  },
  archiveBot(id: string): Promise<Bot> {
    return request(`/api/bots/${id}/archive`, { method: "POST" });
  },
  stopAllBots(): Promise<{ stopped: string[]; failed: { id: string; error: string }[]; count: number }> {
    return request(`/api/bots/stop-all`, { method: "POST" });
  },
  // ──────────── LLM-powered features (Groq) ────────────
  generateStrategy(description: string): Promise<{
    ok: boolean;
    strategy_id?: string;
    param_schema?: Record<string, unknown>;
    file_path?: string;
    note?: string;
    errors?: string[];
    code?: string;
  }> {
    return request(`/api/llm/strategies/generate`, {
      method: "POST",
      body: JSON.stringify({ description }),
    });
  },
  botNarrative(
    botId: string, since_ms: number, until_ms: number, granularity = "hour"
  ): Promise<{ narrative_md: string; window: { since_ms: number; until_ms: number } }> {
    const q = new URLSearchParams({
      since_ms: String(since_ms), until_ms: String(until_ms), granularity,
    });
    return request(`/api/llm/bots/${botId}/narrative?${q}`);
  },
  alertInsights(limit = 50): Promise<{
    groups: { pattern: string; count: number; severity: string;
              likely_cause: string; suggested_action: string }[];
    summary: string;
    input_count: number;
  }> {
    return request(`/api/llm/alerts/insights?limit=${limit}`);
  },
  configSanityCheck(config: BotConfig, diff: DiffEntry[]): Promise<{
    warnings: { severity: "info" | "warning" | "critical"; field: string; message: string }[];
    ok_to_apply: boolean;
    summary: string;
  }> {
    return request(`/api/llm/configs/sanity-check`, {
      method: "POST",
      body: JSON.stringify({ config, diff }),
    });
  },
  listConfigs(botId: string): Promise<ConfigVersion[]> {
    return request(`/api/bots/${botId}/configs`);
  },
  activeConfig(botId: string): Promise<ConfigVersion | null> {
    return request(`/api/bots/${botId}/configs/active`);
  },
  listAdapters(botId: string): Promise<string[]> {
    return request(`/api/bots/${botId}/configs/adapters`);
  },
  createDraft(botId: string, cfg: BotConfig): Promise<ConfigVersion> {
    return request(`/api/bots/${botId}/configs`, {
      method: "POST",
      body: JSON.stringify(cfg),
    });
  },
  validateConfig(botId: string, version: number): Promise<ConfigVersion> {
    return request(`/api/bots/${botId}/configs/${version}/validate`, { method: "POST" });
  },
  diffConfig(botId: string, version: number): Promise<{ changes: DiffEntry[] }> {
    return request(`/api/bots/${botId}/configs/${version}/diff`);
  },
  requestApproval(botId: string, version: number): Promise<ConfigVersion> {
    return request(`/api/bots/${botId}/configs/${version}/request-approval`, { method: "POST" });
  },
  approveConfig(botId: string, version: number): Promise<ConfigVersion> {
    return request(`/api/bots/${botId}/configs/${version}/approve`, { method: "POST" });
  },
  applyConfig(botId: string, version: number, typedConfirmation?: string): Promise<ConfigVersion> {
    return request(`/api/bots/${botId}/configs/${version}/apply`, {
      method: "POST",
      body: JSON.stringify({ typed_confirmation: typedConfirmation ?? null }),
    });
  },
  rollback(botId: string, toVersion: number): Promise<ConfigVersion> {
    return request(`/api/bots/${botId}/configs/rollback/${toVersion}`, { method: "POST" });
  },
  listPositions(botId: string): Promise<Position[]> {
    return request(`/api/bots/${botId}/positions`);
  },
  listOrders(botId: string, limit = 50, since_ms?: number, until_ms?: number): Promise<Order[]> {
    const q = new URLSearchParams({ limit: String(limit) });
    if (since_ms) q.append("since_ms", String(since_ms));
    if (until_ms) q.append("until_ms", String(until_ms));
    return request(`/api/bots/${botId}/orders?${q}`);
  },
  listFills(botId: string, limit = 50, since_ms?: number, until_ms?: number): Promise<Fill[]> {
    const q = new URLSearchParams({ limit: String(limit) });
    if (since_ms) q.append("since_ms", String(since_ms));
    if (until_ms) q.append("until_ms", String(until_ms));
    return request(`/api/bots/${botId}/fills?${q}`);
  },
  listContracts(botId: string, limit = 50, since_ms?: number, until_ms?: number): Promise<Contract[]> {
    const q = new URLSearchParams({ limit: String(limit) });
    if (since_ms) q.append("since_ms", String(since_ms));
    if (until_ms) q.append("until_ms", String(until_ms));
    return request(`/api/bots/${botId}/contracts?${q}`);
  },
  contractsSummary(botId: string, since_ms?: number, until_ms?: number): Promise<ContractsSummary> {
    const params: string[] = [];
    if (since_ms != null) params.push(`since_ms=${since_ms}`);
    if (until_ms != null) params.push(`until_ms=${until_ms}`);
    const q = params.length ? `?${params.join("&")}` : "";
    return request(`/api/bots/${botId}/contracts/summary${q}`);
  },
  brokerBalance(botId: string): Promise<BrokerBalance> {
    return request(`/api/bots/${botId}/balance`);
  },
  resetBalanceBaseline(botId: string): Promise<{ reset: boolean }> {
    return request(`/api/bots/${botId}/balance/reset-baseline`, { method: "POST" });
  },
  listBalanceHistory(botId: string, since_ms?: number, until_ms?: number, max_points = 1000): Promise<BalanceSnapshot[]> {
    const q = new URLSearchParams({ max_points: String(max_points) });
    if (since_ms) q.append("since_ms", String(since_ms));
    if (until_ms) q.append("until_ms", String(until_ms));
    return request(`/api/bots/${botId}/balance/history?${q}`);
  },
  getAnalytics(botId: string, since_ms: number, until_ms: number, granularity = "hour"): Promise<AnalyticsBucket[]> {
    const q = new URLSearchParams({ since_ms: String(since_ms), until_ms: String(until_ms), granularity });
    return request(`/api/bots/${botId}/analytics?${q}`);
  },
  listAudit(resourceId?: string): Promise<AuditEvent[]> {
    const q = resourceId ? `?resource_id=${encodeURIComponent(resourceId)}` : "";
    return request(`/api/audit${q}`);
  },
  listAlerts(): Promise<Alert[]> {
    return request("/api/alerts");
  },
  ackAlert(id: string): Promise<Alert> {
    return request(`/api/alerts/${id}/ack`, { method: "POST" });
  },
  listStrategies(botId: string): Promise<string[]> {
    return request(`/api/bots/${botId}/configs/strategies`);
  },
  strategyParamSchema(botId: string, strategyId: string): Promise<Record<string, unknown>> {
    return request(`/api/bots/${botId}/configs/strategies/${strategyId}/params`);
  },
  runBacktest(body: BacktestRequest): Promise<BacktestMetrics> {
    return request("/api/research/backtest", { method: "POST", body: JSON.stringify(body) });
  },
  listBacktests(): Promise<BacktestMetrics[]> {
    return request("/api/research/backtests");
  },
  totpSetup(): Promise<TOTPSetupResponse> {
    return request("/api/auth/totp/setup", { method: "POST" });
  },
  totpVerify(code: string): Promise<{ totp_enabled: boolean }> {
    return request("/api/auth/totp/verify", { method: "POST", body: JSON.stringify({ code }) });
  },
  totpDisable(): Promise<{ totp_enabled: boolean }> {
    return request("/api/auth/totp", { method: "DELETE" });
  },
  forgotPassword(email: string): Promise<{ detail: string }> {
    return request("/api/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) });
  },
  resetPassword(token: string, new_password: string): Promise<{ detail: string }> {
    return request("/api/auth/reset-password", { method: "POST", body: JSON.stringify({ token, new_password }) });
  },
  listChatSessions(): Promise<ConfigVersion[]> {
    return request("/api/chat/sessions");
  },
  getChatHistory(sessionId: string): Promise<any[]> {
    return request(`/api/chat/sessions/${sessionId}/history`);
  },
  deleteChatSession(sessionId: string): Promise<void> {
    return request(`/api/chat/sessions/${sessionId}`, { method: "DELETE" });
  },
};
