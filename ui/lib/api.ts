/** API client — fetch wrappers + WebSocket for Morphic-Agent backend */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Task API ──

export interface SubTaskResponse {
  id: string;
  description: string;
  status: string;
  dependencies: string[];
  result: string | null;
  error: string | null;
  model_used: string | null;
  cost_usd: number;
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

export function createTask(goal: string) {
  return request<TaskResponse>("/api/tasks", {
    method: "POST",
    body: JSON.stringify({ goal }),
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

// ── WebSocket ──

export function connectTaskWs(
  taskId: string,
  onMessage: (data: TaskResponse) => void,
  onClose?: () => void,
): WebSocket {
  const wsBase = API_BASE.replace(/^http/, "ws");
  const ws = new WebSocket(`${wsBase}/ws/tasks/${taskId}`);
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  ws.onclose = () => onClose?.();
  return ws;
}
