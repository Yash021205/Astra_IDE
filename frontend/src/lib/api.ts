// API client for the ASTRA-IDE backend (FastAPI).
// Reads JWT from the Zustand auth store (which persists to localStorage).
// Rewrites /api/* to the backend via Next.js rewrites.
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  withCredentials: false,
});

api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    // Read directly from localStorage to avoid a circular import with auth.ts.
    // Zustand's persist middleware stores under key `astra-auth` as JSON:
    //   { "state": { "token": "...", "user": {...} }, "version": 0 }
    const raw = window.localStorage.getItem('astra-auth');
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as { state?: { token?: string } };
        const token = parsed?.state?.token;
        if (token) {
          config.headers = config.headers ?? {};
          config.headers.Authorization = `Bearer ${token}`;
        }
      } catch {
        /* corrupt storage — ignore */
      }
    }
  }
  return config;
});

// ── Types matching backend schemas ─────────────────────────────────────────

export interface User {
  id: number;
  email: string;
  username: string;
  trust_score: number;
  preferred_lang: string;
}

export interface TokenResponse {
  access_token: string;
  token_type:   string;
  user:         User;
}

export interface Workspace {
  id: number;
  name: string;
  language: string;
  status: 'PENDING' | 'PREWARMED' | 'RUNNING' | 'STOPPED' | 'FAILED' | 'ARCHIVED';
  sandbox_tier: 'runc' | 'gvisor' | 'firecracker';
  risk_score: number;
  network_access: boolean;
  filesystem_write: boolean;
  cpu_request: number;
  memory_request: number;
  cluster_id: string;
  node_name: string;
  pod_name: string;
  yjs_room: string;
  owner_id: number;
  created_at: string;
  updated_at: string;
  last_active_at: string;
}

export interface WorkspaceCreate {
  name: string;
  language: string;
  network_access?: boolean;
  filesystem_write?: boolean;
  cpu_request?: number;
  memory_request?: number;
  initial_code?: string;
}

// ── Auth ────────────────────────────────────────────────────────────────────

export async function register(email: string, username: string, password: string): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>('/auth/register', { email, username, password });
  return data;
}

export async function login(username_or_email: string, password: string): Promise<TokenResponse> {
  // FastAPI's OAuth2PasswordRequestForm expects form-encoded body
  const form = new URLSearchParams();
  form.append('username', username_or_email);
  form.append('password', password);
  const { data } = await api.post<TokenResponse>('/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  return data;
}

export async function fetchMe(): Promise<User> {
  const { data } = await api.get<User>('/auth/me');
  return data;
}

// ── Workspaces ──────────────────────────────────────────────────────────────

export async function listWorkspaces(): Promise<Workspace[]> {
  const { data } = await api.get<{ total: number; items: Workspace[] }>('/workspaces');
  return data.items;
}

export async function createWorkspace(payload: WorkspaceCreate): Promise<Workspace> {
  const { data } = await api.post<Workspace>('/workspaces', payload);
  return data;
}

export async function getWorkspace(id: number): Promise<Workspace> {
  const { data } = await api.get<Workspace>(`/workspaces/${id}`);
  return data;
}

export async function startWorkspace(id: number): Promise<Workspace> {
  const { data } = await api.post<Workspace>(`/workspaces/${id}/start`);
  return data;
}

export async function stopWorkspace(id: number): Promise<Workspace> {
  const { data } = await api.post<Workspace>(`/workspaces/${id}/stop`);
  return data;
}

export async function deleteWorkspace(id: number): Promise<void> {
  await api.delete(`/workspaces/${id}`);
}

// ── Sharing ────────────────────────────────────────────────────────────────

export interface WorkspaceMember {
  user_id:  number;
  username: string;
  role:     'owner' | 'editor' | 'viewer';
  added_at: string;
}

export async function shareWorkspace(
  id: number, username: string, role: 'editor' | 'viewer' = 'editor',
): Promise<{ user_id: number; username: string; role: string }> {
  const { data } = await api.post(`/workspaces/${id}/share`, { username, role });
  return data;
}

export async function listMembers(id: number): Promise<WorkspaceMember[]> {
  const { data } = await api.get<{ total: number; items: WorkspaceMember[] }>(
    `/workspaces/${id}/members`,
  );
  return data.items;
}

export async function revokeMember(workspaceId: number, userId: number): Promise<void> {
  await api.delete(`/workspaces/${workspaceId}/members/${userId}`);
}

// ── Code execution ─────────────────────────────────────────────────────────

export interface ExecuteResponse {
  language:   string;
  exit_code:  number;
  stdout:     string;
  stderr:     string;
  runtime_ms: number;
  timeout:    boolean;
  truncated:  boolean;
}

export async function executeCode(
  workspaceId: number, language: string, code: string, stdin?: string,
): Promise<ExecuteResponse> {
  const { data } = await api.post<ExecuteResponse>(
    `/workspaces/${workspaceId}/execute`,
    { language, code, stdin },
  );
  return data;
}

// ── Carbon ─────────────────────────────────────────────────────────────────

export interface CarbonReading {
  zone:             string;
  carbon_intensity: number;
  is_estimated:     boolean;
  is_fallback:      boolean;
  source:           string;
  timestamp:        number;
}

export async function getCarbonIntensity(zone: string): Promise<CarbonReading> {
  const { data } = await api.get<CarbonReading>(`/carbon/intensity?zone=${encodeURIComponent(zone)}`);
  return data;
}

// ── Events / Activity feed ─────────────────────────────────────────────────

export interface SchedulerEvent {
  id:           number;
  timestamp:    string;
  kind:         'scheduler' | 'sandbox' | 'ebpf' | 'carbon' | 'prewarm' | 'collab' | 'system';
  title:        string;
  detail:       string;
  workspace_id: number;
  cluster_id:   string;
  node_name:    string;
}

export async function listEvents(opts: { limit?: number; kind?: string } = {}):
  Promise<SchedulerEvent[]> {
  const params = new URLSearchParams();
  if (opts.limit) params.set('limit', String(opts.limit));
  if (opts.kind)  params.set('kind', opts.kind);
  const { data } = await api.get<{ total: number; items: SchedulerEvent[] }>(
    `/events?${params.toString()}`,
  );
  return data.items;
}

// ── Live cluster + node metrics ────────────────────────────────────────────

export interface NodeMetrics {
  cluster_id:    string;
  node_name:     string;
  cpu_util:      number;
  memory_util:   number;
  network_kbps:  number;
  run_queue_len: number;
  active_pods:   number;
}

export interface ClusterMetrics {
  cluster_id:   string;
  location:     string;
  carbon_gco2:  number;
  total_pods:   number;
  nodes:        NodeMetrics[];
}

export interface MetricsSnapshot {
  timestamp: string;
  clusters:  ClusterMetrics[];
}

export async function getNodeMetrics(): Promise<MetricsSnapshot> {
  const { data } = await api.get<MetricsSnapshot>('/metrics/nodes');
  return data;
}

// ── Benchmarks ─────────────────────────────────────────────────────────────

export interface BenchmarkRow {
  algorithm:       string;
  avg_latency_ms:  number;
  p95_latency_ms:  number;
  utilization_pct: number;
  balance_score:   number;
  energy_kwh:      number;
  sla_violations:  number;
}

export interface BenchmarkReport {
  description: string;
  rows:        BenchmarkRow[];
  metadata:    Record<string, string>;
}

export async function runBenchmark(n_jobs = 200, seed = 42): Promise<BenchmarkReport> {
  const { data } = await api.get<BenchmarkReport>(
    `/benchmarks/run?n_jobs=${n_jobs}&seed=${seed}`,
  );
  return data;
}

export default api;
