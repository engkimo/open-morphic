/** API client — fetch wrappers + WebSocket for Morphic-Agent backend */

import { logger } from "./logger";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method || "GET";
  logger.info(`API ${method} ${path}`);
  const start = performance.now();
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10_000);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      signal: controller.signal,
    });
    const elapsed = Math.round(performance.now() - start);
    if (!res.ok) {
      logger.error(`API ${method} ${path} — ${res.status} ${res.statusText} (${elapsed}ms)`);
      throw new Error(`API error: ${res.status} ${res.statusText}`);
    }
    logger.info(`API ${method} ${path} — ${res.status} (${elapsed}ms)`);
    if (res.status === 204) return undefined as T;
    return res.json();
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      const elapsed = Math.round(performance.now() - start);
      logger.error(`API ${method} ${path} — timeout (${elapsed}ms)`);
      throw new Error("API request timed out");
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

// ── Task API ──

export interface SubTaskResponse {
  id: string;
  description: string;
  status: string;
  dependencies: string[];
  result: string | null;
  error: string | null;
  code: string | null;
  execution_output: string | null;
  model_used: string | null;
  cost_usd: number;
  complexity: string | null;
  tool_calls_count?: number;
  react_iterations?: number;
  engine_used?: string | null;
  tools_used?: string[];
  data_sources?: string[];
  preferred_model?: string | null;
  spawned_by_reflection?: boolean;
  reflection_round?: number | null;
}

export interface TaskResponse {
  id: string;
  goal: string;
  status: string;
  subtasks: SubTaskResponse[];
  total_cost_usd: number;
  created_at: string;
  is_complete: boolean;
  success_rate: number;
}

export interface TaskListResponse {
  tasks: TaskResponse[];
  count: number;
}

export interface CreateTaskOptions {
  engine?: string | null;
  fractal_max_depth?: number | null;
  fractal_max_concurrent_nodes?: number | null;
  fractal_throttle_delay_ms?: number | null;
}

export function createTask(goal: string, options?: CreateTaskOptions | string | null) {
  // Backwards compat: accept bare engine string
  const opts: CreateTaskOptions =
    typeof options === "string" ? { engine: options } : options ?? {};
  return request<TaskResponse>("/api/tasks", {
    method: "POST",
    body: JSON.stringify({
      goal,
      engine: opts.engine || null,
      ...(opts.fractal_max_depth != null && { fractal_max_depth: opts.fractal_max_depth }),
      ...(opts.fractal_max_concurrent_nodes != null && {
        fractal_max_concurrent_nodes: opts.fractal_max_concurrent_nodes,
      }),
      ...(opts.fractal_throttle_delay_ms != null && {
        fractal_throttle_delay_ms: opts.fractal_throttle_delay_ms,
      }),
    }),
  });
}

export function listTasks() {
  return request<TaskListResponse>("/api/tasks");
}

export function getTask(id: string) {
  return request<TaskResponse>(`/api/tasks/${id}`);
}

export function deleteTask(id: string) {
  return request<void>(`/api/tasks/${id}`, { method: "DELETE" });
}

// ── Plan API ──

export interface PlanStepResponse {
  subtask_description: string;
  proposed_model: string;
  estimated_cost_usd: number;
  estimated_tokens: number;
  risk_note: string;
}

export interface ExecutionPlanResponse {
  id: string;
  goal: string;
  steps: PlanStepResponse[];
  total_estimated_cost_usd: number;
  status: string;
  task_id: string | null;
  created_at: string;
}

export interface PlanListResponse {
  plans: ExecutionPlanResponse[];
  count: number;
}

export function createPlan(goal: string, model: string = "ollama/qwen3:8b") {
  return request<ExecutionPlanResponse>("/api/plans", {
    method: "POST",
    body: JSON.stringify({ goal, model }),
  });
}

export function getPlan(id: string) {
  return request<ExecutionPlanResponse>(`/api/plans/${id}`);
}

export function listPlans() {
  return request<PlanListResponse>("/api/plans");
}

export function approvePlan(id: string) {
  return request<TaskResponse>(`/api/plans/${id}/approve`, {
    method: "POST",
  });
}

export function rejectPlan(id: string) {
  return request<ExecutionPlanResponse>(`/api/plans/${id}/reject`, {
    method: "POST",
  });
}

// ── Cost API ──

export interface CostSummary {
  daily_total_usd: number;
  monthly_total_usd: number;
  local_usage_rate: number;
  monthly_budget_usd: number;
  budget_remaining_usd: number;
}

export function getCostSummary() {
  return request<CostSummary>("/api/cost");
}

// ── Model API ──

export interface ModelStatus {
  ollama_running: boolean;
  default_model: string;
  models: { name: string; available: boolean }[];
}

export function getModelStatus() {
  return request<ModelStatus>("/api/models/status");
}

// ── Marketplace API ──

export interface ToolCandidateResponse {
  name: string;
  description: string;
  publisher: string;
  package_name: string;
  transport: string;
  install_command: string;
  source_url: string;
  download_count: number;
  safety_tier: string;
  safety_score: number;
}

export interface ToolSearchResponse {
  query: string;
  candidates: ToolCandidateResponse[];
  total_count: number;
  error: string | null;
}

export interface ToolInstallResponse {
  tool_name: string;
  success: boolean;
  message: string;
  error: string | null;
}

export function searchTools(query: string, limit: number = 10) {
  return request<ToolSearchResponse>(
    `/api/marketplace/search?q=${encodeURIComponent(query)}&limit=${limit}`,
  );
}

export function installTool(name: string) {
  return request<ToolInstallResponse>("/api/marketplace/install", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function listInstalledTools() {
  return request<ToolCandidateResponse[]>("/api/marketplace/installed");
}

export function uninstallTool(name: string) {
  return request<ToolInstallResponse>(`/api/marketplace/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
}

// ── Model Management API ──

export function pullModel(name: string) {
  return request<{ name: string; success: boolean }>("/api/models/pull", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function deleteModel(name: string) {
  return request<{ name: string; deleted: boolean }>(
    `/api/models/${encodeURIComponent(name)}`,
    { method: "DELETE" },
  );
}

export function switchModel(name: string) {
  return request<{ name: string; default: boolean }>("/api/models/switch", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function getRunningModels() {
  return request<Record<string, unknown>[]>("/api/models/running");
}

// ── Evolution API ──

export interface ExecutionStatsResponse {
  total_count: number;
  success_count: number;
  failure_count: number;
  success_rate: number;
  avg_cost_usd: number;
  avg_duration_seconds: number;
  model_distribution: Record<string, number>;
  engine_distribution: Record<string, number>;
}

export interface FailurePattern {
  error_pattern: string;
  count: number;
  task_types: string[];
  engines: string[];
}

export interface FailurePatternsResponse {
  patterns: FailurePattern[];
  count: number;
}

export interface ModelPreference {
  task_type: string;
  model: string;
  success_rate: number;
  avg_cost_usd: number;
  avg_duration_seconds: number;
  sample_count: number;
}

export interface EnginePreference {
  task_type: string;
  engine: string;
  success_rate: number;
  avg_cost_usd: number;
  avg_duration_seconds: number;
  sample_count: number;
}

export interface PreferencesResponse {
  model_preferences: ModelPreference[];
  engine_preferences: EnginePreference[];
}

export interface StrategyUpdateResponse {
  model_preferences_updated: number;
  engine_preferences_updated: number;
  recovery_rules_added: number;
  details: string[];
}

export interface EvolutionReportResponse {
  level: string;
  strategy_update: StrategyUpdateResponse | null;
  tool_gaps_found: number;
  tools_suggested: string[];
  summary: string;
  created_at: string;
}

export function getEvolutionStats(taskType?: string) {
  const params = taskType ? `?task_type=${encodeURIComponent(taskType)}` : "";
  return request<ExecutionStatsResponse>(`/api/evolution/stats${params}`);
}

export function getFailurePatterns(limit: number = 20) {
  return request<FailurePatternsResponse>(
    `/api/evolution/failures?limit=${limit}`,
  );
}

export function getPreferences() {
  return request<PreferencesResponse>("/api/evolution/preferences");
}

export function triggerStrategyUpdate() {
  return request<StrategyUpdateResponse>("/api/evolution/update", {
    method: "POST",
  });
}

export function triggerEvolution() {
  return request<EvolutionReportResponse>("/api/evolution/evolve", {
    method: "POST",
  });
}

// ── Cognitive / UCL API ──

export interface DecisionResponse {
  id: string;
  description: string;
  rationale: string;
  agent_engine: string;
  confidence: number;
  timestamp: string;
}

export interface AgentActionResponse {
  id: string;
  agent_engine: string;
  action_type: string;
  summary: string;
  cost_usd: number;
  duration_seconds: number;
  timestamp: string;
}

export interface SharedTaskStateResponse {
  task_id: string;
  decisions: DecisionResponse[];
  artifacts: Record<string, string>;
  blockers: string[];
  agent_history: AgentActionResponse[];
  last_agent: string | null;
  total_cost_usd: number;
  created_at: string;
  updated_at: string;
}

export interface SharedTaskStateListResponse {
  states: SharedTaskStateResponse[];
  count: number;
}

export interface AffinityScoreResponse {
  engine: string;
  topic: string;
  familiarity: number;
  recency: number;
  success_rate: number;
  cost_efficiency: number;
  sample_count: number;
  score: number;
  last_used: string | null;
}

export interface AffinityListResponse {
  scores: AffinityScoreResponse[];
  count: number;
}

export function getCognitiveStates() {
  return request<SharedTaskStateListResponse>("/api/cognitive/state");
}

export function getCognitiveState(taskId: string) {
  return request<SharedTaskStateResponse>(
    `/api/cognitive/state/${encodeURIComponent(taskId)}`,
  );
}

export function deleteCognitiveState(taskId: string) {
  return request<void>(
    `/api/cognitive/state/${encodeURIComponent(taskId)}`,
    { method: "DELETE" },
  );
}

export function getAffinityScores(params?: {
  topic?: string;
  engine?: string;
}) {
  const searchParams = new URLSearchParams();
  if (params?.topic) searchParams.set("topic", params.topic);
  if (params?.engine) searchParams.set("engine", params.engine);
  const qs = searchParams.toString();
  return request<AffinityListResponse>(
    `/api/cognitive/affinity${qs ? `?${qs}` : ""}`,
  );
}

// ── Benchmarks API ──

export interface AdapterScoreResponse {
  engine: string;
  decisions_injected: number;
  decisions_found: number;
  artifacts_injected: number;
  artifacts_found: number;
  blockers_injected: number;
  blockers_found: number;
  context_length: number;
  score: number;
}

export interface ContinuityResultResponse {
  overall_score: number;
  adapter_scores: AdapterScoreResponse[];
}

export interface DedupScoreResponse {
  scenario: string;
  engine_a: string;
  engine_b: string;
  raw_count_a: number;
  raw_count_b: number;
  total_raw: number;
  deduped_count: number;
  dedup_rate: number;
}

export interface DedupResultResponse {
  overall_accuracy: number;
  scores: DedupScoreResponse[];
}

export interface BenchmarkResultResponse {
  overall_score: number;
  context_continuity: ContinuityResultResponse | null;
  dedup_accuracy: DedupResultResponse | null;
  errors: string[];
  timestamp: string;
}

export function runBenchmarks() {
  return request<BenchmarkResultResponse>("/api/benchmarks/run", {
    method: "POST",
  });
}

export function runContinuityBenchmark() {
  return request<BenchmarkResultResponse>("/api/benchmarks/continuity", {
    method: "POST",
  });
}

export function runDedupBenchmark() {
  return request<BenchmarkResultResponse>("/api/benchmarks/dedup", {
    method: "POST",
  });
}

// ── Engine API ──

export interface EngineInfoResponse {
  engine_type: string;
  available: boolean;
  max_context_tokens: number;
  supports_sandbox: boolean;
  supports_parallel: boolean;
  supports_mcp: boolean;
  cost_per_hour_usd: number;
}

export interface EngineListResponse {
  engines: EngineInfoResponse[];
  count: number;
}

export interface FallbackAttemptResponse {
  engine: string;
  attempted: boolean;
  skip_reason: string | null;
  error: string | null;
  duration_seconds: number;
}

export interface EngineRunRequest {
  task: string;
  engine?: string | null;
  task_type?: string;
  budget?: number;
  model?: string | null;
  timeout_seconds?: number;
  context?: string | null;
}

export interface EngineRunResponse {
  engine: string;
  success: boolean;
  output: string;
  cost_usd: number;
  duration_seconds: number;
  model_used: string | null;
  error: string | null;
  fallback_reason: string | null;
  engines_tried: string[];
  fallback_attempts: FallbackAttemptResponse[];
}

export function listEngines() {
  return request<EngineListResponse>("/api/engines");
}

export function getEngine(engineType: string) {
  return request<EngineInfoResponse>(
    `/api/engines/${encodeURIComponent(engineType)}`,
  );
}

export function runEngine(body: EngineRunRequest) {
  return request<EngineRunResponse>("/api/engines/run", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ── Cost Log API ──

export interface CostLogEntry {
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  is_local: boolean;
  timestamp: string;
}

export interface CostLogResponse {
  logs: CostLogEntry[];
  count: number;
}

export function getCostLogs(limit: number = 50) {
  return request<CostLogResponse>(`/api/cost/logs?limit=${limit}`);
}

// ── Memory API ──

export interface MemorySearchResponse {
  query: string;
  results: string[];
  count: number;
}

export interface ContextExportResponse {
  platform: string;
  content: string;
  token_estimate: number;
}

export function searchMemory(query: string) {
  return request<MemorySearchResponse>(
    `/api/memory/search?q=${encodeURIComponent(query)}`,
  );
}

export function exportContext(platform: string, query: string = "") {
  const params = new URLSearchParams({ platform });
  if (query) params.set("q", query);
  return request<ContextExportResponse>(`/api/memory/export?${params}`);
}

// ── A2A Protocol API ──

export interface A2AMessageResponse {
  id: string;
  sender: string;
  receiver: string | null;
  message_type: string;
  action: string;
  task_id: string;
  conversation_id: string;
  payload: string;
  artifacts: Record<string, string>;
  timestamp: string;
}

export interface ConversationResponse {
  id: string;
  task_id: string;
  participants: string[];
  status: string;
  message_count: number;
  response_count: number;
  pending_count: number;
  created_at: string;
  resolved_at: string | null;
  messages: A2AMessageResponse[];
}

export interface ConversationCheckResponse {
  expired: boolean;
  complete: boolean;
  status: string;
}

export interface CollectRepliesResponse {
  new_replies: number;
  total_messages: number;
}

export interface SendResultResponse {
  message_id: string;
  conversation_id: string;
  receiver: string | null;
  routed: boolean;
}

export interface AgentDescriptorResponse {
  agent_id: string;
  engine_type: string;
  capabilities: string[];
  status: string;
  last_seen: string;
}

export interface AgentListResponse {
  agents: AgentDescriptorResponse[];
  count: number;
}

export function createConversation(
  taskId: string,
  participants: string[],
  ttlSeconds: number = 300,
) {
  return request<ConversationResponse>("/api/a2a/conversations", {
    method: "POST",
    body: JSON.stringify({
      task_id: taskId,
      participants,
      ttl_seconds: ttlSeconds,
    }),
  });
}

export function getConversation(conversationId: string) {
  return request<ConversationResponse>(
    `/api/a2a/conversations/${encodeURIComponent(conversationId)}`,
  );
}

export function checkConversation(conversationId: string) {
  return request<ConversationCheckResponse>(
    `/api/a2a/conversations/${encodeURIComponent(conversationId)}/check`,
    { method: "POST" },
  );
}

export function collectReplies(conversationId: string) {
  return request<CollectRepliesResponse>(
    `/api/a2a/conversations/${encodeURIComponent(conversationId)}/collect`,
    { method: "POST" },
  );
}

export function sendA2AMessage(
  conversationId: string,
  sender: string,
  action: string,
  payload: string,
  receiver?: string,
  artifacts?: Record<string, string>,
) {
  return request<SendResultResponse>(
    `/api/a2a/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      method: "POST",
      body: JSON.stringify({ sender, action, payload, receiver, artifacts }),
    },
  );
}

export function replyA2AMessage(
  conversationId: string,
  sender: string,
  messageId: string,
  payload: string,
  artifacts?: Record<string, string>,
) {
  return request<SendResultResponse>(
    `/api/a2a/conversations/${encodeURIComponent(conversationId)}/reply`,
    {
      method: "POST",
      body: JSON.stringify({
        sender,
        message_id: messageId,
        payload,
        artifacts,
      }),
    },
  );
}

export function listAgents() {
  return request<AgentListResponse>("/api/a2a/agents");
}

export function registerAgent(engineType: string, capabilities: string[]) {
  return request<AgentDescriptorResponse>("/api/a2a/agents", {
    method: "POST",
    body: JSON.stringify({ engine_type: engineType, capabilities }),
  });
}

export function deregisterAgent(agentId: string) {
  return request<void>(`/api/a2a/agents/${encodeURIComponent(agentId)}`, {
    method: "DELETE",
  });
}

// ── Settings API ──

export interface FractalSettings {
  max_depth: number;
  candidates_per_node: number;
  max_concurrent_nodes: number;
  throttle_delay_ms: number;
  max_total_nodes: number;
  max_reflection_rounds: number;
}

export interface FractalSettingsUpdate {
  max_depth?: number | null;
  max_concurrent_nodes?: number | null;
  throttle_delay_ms?: number | null;
  candidates_per_node?: number | null;
  max_total_nodes?: number | null;
  max_reflection_rounds?: number | null;
}

export interface SettingsResponse {
  version: string;
  environment: string;
  planning_mode: string;
  local_first: boolean;
  execution_engine: string;
  budget: { monthly_usd: number; task_usd: number; auto_downgrade: boolean };
  ollama: { base_url: string; default_model: string };
  engines: {
    claude_code_enabled: boolean;
    gemini_cli_enabled: boolean;
    codex_cli_enabled: boolean;
    openhands_base_url: string;
    default_engine: string;
  };
  mcp: { enabled: boolean; transport: string };
  laee: { enabled: boolean; approval_mode: string };
  api_keys_configured: { anthropic: boolean; openai: boolean; gemini: boolean };
  fractal: FractalSettings;
}

export interface HealthCheck {
  name: string;
  status: string;
}

export interface HealthResponse {
  overall: string;
  checks: HealthCheck[];
}

export function getSettings() {
  return request<SettingsResponse>("/api/settings");
}

export function getHealth() {
  return request<HealthResponse>("/api/settings/health");
}

export function updateFractalSettings(body: FractalSettingsUpdate) {
  return request<{ updated: Record<string, number>; fractal: FractalSettings }>(
    "/api/settings/fractal",
    { method: "PUT", body: JSON.stringify(body) },
  );
}

// ── WebSocket ──

export function connectTaskWs(
  taskId: string,
  onMessage: (data: TaskResponse) => void,
  onClose?: () => void,
): WebSocket {
  const wsBase = API_BASE.replace(/^http/, "ws");
  logger.info(`WebSocket connecting — task=${taskId}`);
  const ws = new WebSocket(`${wsBase}/ws/tasks/${taskId}`);
  ws.onopen = () => logger.info(`WebSocket connected — task=${taskId}`);
  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    logger.debug(`WebSocket message — task=${taskId} status=${data.status}`);
    onMessage(data);
  };
  ws.onclose = () => {
    logger.info(`WebSocket closed — task=${taskId}`);
    onClose?.();
  };
  ws.onerror = (e) => logger.error(`WebSocket error — task=${taskId}`, e);
  return ws;
}
