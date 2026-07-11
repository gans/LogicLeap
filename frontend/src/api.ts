export const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

export interface Actor { id: string; display_name: string; kind: string }
export interface Epic {
  id: string; title: string; summary: string; problem_statement: string;
  desired_outcome: string; architect_actor_id: string; version: number; created_at: string;
}
export interface Task {
  id: string; epic_id: string; title: string; summary: string; objective: string;
  state: string; blocked_from_state: string | null; architect_actor_id: string;
  version: number; created_at: string;
}
export interface WorkingContext {
  task: Task;
  actors: Record<string, unknown>[];
  requirements: Record<string, unknown>[];
  acceptance_criteria: Record<string, unknown>[];
  context_entries: Record<string, unknown>[];
  questions: Record<string, unknown>[];
  blockers: Record<string, unknown>[];
  decisions: Record<string, unknown>[];
  implementation_runs: Record<string, unknown>[];
  evidence: Record<string, unknown>[];
  reviews: Record<string, unknown>[];
  timeline: Record<string, unknown>[];
  allowed_transitions: { target_state: string; ready: boolean; missing: { code: string; message: string }[]; suggested: boolean }[];
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.message ?? body.detail?.message ?? JSON.stringify(body.detail));
  }
  return response.json() as Promise<T>;
}
