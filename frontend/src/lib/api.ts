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
  avatar_url?: string | null;
  is_admin?: boolean;
  github_login?: string | null;  // null = GitHub not linked
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
  forked_from_id?: number | null;
  frozen?: boolean;
  created_at: string;
  updated_at: string;
  last_active_at: string;
}

export type SandboxTier = 'runc' | 'gvisor' | 'firecracker';

export interface WorkspaceCreate {
  name: string;
  language: string;
  network_access?: boolean;
  filesystem_write?: boolean;
  cpu_request?: number;
  memory_request?: number;
  initial_code?: string;
  /** null/undefined = Auto (adaptive risk-scored tier); or pin explicitly. */
  sandbox_override?: SandboxTier | null;
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

// Load the current user with an explicit token (used by the OAuth callback,
// before the token has been persisted to localStorage for the interceptor).
export async function fetchMeWithToken(token: string): Promise<User> {
  const { data } = await api.get<User>('/auth/me', {
    headers: { Authorization: `Bearer ${token}` },
  });
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

export async function updateWorkspace(
  id: number,
  payload: { name?: string; sandbox_override?: SandboxTier },
): Promise<Workspace> {
  const { data } = await api.patch<Workspace>(`/workspaces/${id}`, payload);
  return data;
}

// ── Sharing ────────────────────────────────────────────────────────────────

export interface WorkspaceMember {
  user_id:  number;
  username: string;
  email?:   string | null;
  avatar_url?: string | null;
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

// ── Workspace files + GitHub import ────────────────────────────────────────

export interface WsFile { path: string; type: 'file' | 'dir'; size?: number; }

export async function importRepo(workspaceId: number, gitUrl: string):
  Promise<{ ok: boolean; detail: string; file_count: number }> {
  const { data } = await api.post(`/workspaces/${workspaceId}/import-repo`, { git_url: gitUrl });
  return data;
}
export async function listFiles(workspaceId: number): Promise<WsFile[]> {
  const { data } = await api.get<{ files: WsFile[] }>(`/workspaces/${workspaceId}/files`);
  return data.files;
}
export async function readFile(workspaceId: number, path: string): Promise<string> {
  const { data } = await api.get<{ content: string }>(
    `/workspaces/${workspaceId}/file?path=${encodeURIComponent(path)}`);
  return data.content;
}
export async function writeFile(workspaceId: number, path: string, content: string): Promise<void> {
  await api.put(`/workspaces/${workspaceId}/file`, { path, content });
}
export async function makeDir(workspaceId: number, path: string): Promise<void> {
  await api.post(`/workspaces/${workspaceId}/mkdir`, { path });
}
export async function deletePath(workspaceId: number, path: string): Promise<void> {
  await api.delete(`/workspaces/${workspaceId}/file?path=${encodeURIComponent(path)}`);
}
export async function snapshotWorkspace(workspaceId: number):
  Promise<{ ok: boolean; detail: string; key: string; size: number }> {
  const { data } = await api.post(`/workspaces/${workspaceId}/snapshot`);
  return data;
}

export interface SearchHit { path: string; line: number; text: string; }
export async function searchWorkspace(workspaceId: number, q: string): Promise<SearchHit[]> {
  const { data } = await api.get<{ results: SearchHit[] }>(
    `/workspaces/${workspaceId}/search?q=${encodeURIComponent(q)}`);
  return data.results;
}

export async function forkWorkspace(workspaceId: number): Promise<Workspace> {
  const { data } = await api.post<Workspace>(`/workspaces/${workspaceId}/fork`);
  return data;
}

/** Raw-file URL for <img> previews (token in query since img can't set headers). */
function authToken(): string {
  try {
    const raw = window.localStorage.getItem('astra-auth');
    return raw ? (JSON.parse(raw)?.state?.token ?? '') : '';
  } catch { return ''; }
}

export function rawFileUrl(workspaceId: number, path: string): string {
  return `/api/workspaces/${workspaceId}/raw?path=${encodeURIComponent(path)}&token=${encodeURIComponent(authToken())}`;
}

/** Static-preview URL for an in-iframe live preview (serves workspace files). */
export function previewUrl(workspaceId: number, path = 'index.html'): string {
  return `/api/workspaces/${workspaceId}/preview/${path}?token=${encodeURIComponent(authToken())}`;
}

/** Live-server preview: reverse-proxy a dev server running inside the container on `port`. */
export function proxyUrl(workspaceId: number, port: number, path = ''): string {
  return `/api/workspaces/${workspaceId}/proxy/${port}/${path}?token=${encodeURIComponent(authToken())}`;
}

/** Ports a dev server is listening on inside the running workspace container. */
export async function getWorkspacePorts(workspaceId: number): Promise<number[]> {
  const { data } = await api.get<{ ports: number[] }>(`/workspaces/${workspaceId}/ports`);
  return data.ports ?? [];
}

// ── Change history / exclusions / freeze ─────────────────────────────────────

export interface EditEntry {
  username: string; path: string; lines_added: number; lines_removed: number; created_at: string;
}
export async function getHistory(workspaceId: number): Promise<EditEntry[]> {
  const { data } = await api.get<EditEntry[]>(`/workspaces/${workspaceId}/history`);
  return data;
}
export async function getExcludes(workspaceId: number): Promise<string[]> {
  const { data } = await api.get<{ excludes: string[] }>(`/workspaces/${workspaceId}/excludes`);
  return data.excludes;
}
export async function setExcludes(workspaceId: number, excludes: string[]): Promise<void> {
  await api.put(`/workspaces/${workspaceId}/excludes`, { excludes });
}
export async function setFrozen(workspaceId: number, frozen: boolean): Promise<Workspace> {
  const { data } = await api.patch<Workspace>(`/workspaces/${workspaceId}`, { frozen });
  return data;
}

// ── Profile (avatar via imgbb) ───────────────────────────────────────────────

export async function updateProfile(avatar_url: string): Promise<User> {
  const { data } = await api.patch<User>('/auth/me', { avatar_url });
  return data;
}

const IMGBB_KEY = '867d7e2c0a3447bae67174900d476c9f';
/** Upload an image to imgbb and return the hosted URL. */
export async function uploadToImgbb(file: File): Promise<string> {
  const form = new FormData();
  form.append('image', file);
  const res = await fetch(`https://api.imgbb.com/1/upload?key=${IMGBB_KEY}`, {
    method: 'POST', body: form,
  });
  const json = await res.json();
  if (!json?.data?.url) throw new Error(json?.error?.message || 'Upload failed');
  return json.data.url as string;
}

// ── System status (live infra backends) ────────────────────────────────────

export interface SystemStatus {
  environment:   string;
  database:      string;
  cache_backend: string;
  object_store:  string;
  metrics:       string;
  carbon_api:    string;
  google_oauth:  string;
}

export async function getSystemStatus(): Promise<SystemStatus> {
  const { data } = await api.get<SystemStatus>('/system/status');
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

export interface BenchmarkRunLog {
  id:               number;
  created_at:       string;
  username:         string;
  n_jobs:           number;
  seed:             number;
  winner:           string;
  ppo_latency_ms:   number;
  ppo_util_pct:     number;
  ppo_balance:      number;
  ppo_sla:          number;
  latency_gain_pct: number;
}

export async function getBenchmarkHistory(limit = 20): Promise<BenchmarkRunLog[]> {
  const { data } = await api.get<BenchmarkRunLog[]>(`/benchmarks/history?limit=${limit}`);
  return data;
}

// ── Scheduler comparison ─────────────────────────────────────────────────────
export interface SchedulerChoice {
  algorithm: string; label: string; cluster_id: string; node_name: string;
  score: number; reasoning: string;
}
export interface SchedulerCompareResponse {
  workload: { cpu: number; memory: number; tier: string; language: string };
  results: SchedulerChoice[];
}
export async function compareSchedulers(
  p: { cpu: number; memory: number; tier: string; language: string },
): Promise<SchedulerCompareResponse> {
  const { data } = await api.get<SchedulerCompareResponse>('/scheduler/compare', { params: p });
  return data;
}

// ── Admin ──────────────────────────────────────────────────────────────────
export interface AdminWorkspace {
  id: number; name: string; language: string; sandbox_tier: string; status: string;
  cpu_cores?: number | null; memory_mb?: number | null; cluster_id?: string | null; risk_score?: number | null;
}
export interface AdminUser {
  id: number; username: string; email: string; is_admin: boolean; trust_score: number;
  created_at: string; avatar_url?: string | null;
  workspace_count: number; running_count: number;
  tiers: Record<string, number>; total_cpu: number; total_mem_mb: number;
  edits: number; shares: number; benchmark_runs: number;
  features: string[]; workspaces: AdminWorkspace[];
}
export interface AdminOverview {
  total_users: number; total_workspaces: number; running_workspaces: number;
  total_edits: number; total_benchmark_runs: number; users: AdminUser[];
}
export async function getAdminUsers(): Promise<AdminOverview> {
  const { data } = await api.get<AdminOverview>('/admin/users');
  return data;
}

// ── Sandbox observability ────────────────────────────────────────────────────
export interface SandboxTierMetric {
  tier: string; label: string; startup_ms: number; cpu_overhead_pct: number;
  syscall_us: number; memory_mb: number; isolation: string;
}
export interface SandboxMetrics {
  timestamp: string; tiers: SandboxTierMetric[]; note: string;
}
export async function getSandboxMetrics(): Promise<SandboxMetrics> {
  const { data } = await api.get<SandboxMetrics>('/metrics/sandbox');
  return data;
}

// ── Pods (container management) ──────────────────────────────────────────────
export interface PodInfo {
  id: number; name: string; status: string; language: string; sandbox_tier: string;
  runtime_class: string; image: string; cluster_id: string; node_name: string; pod_name: string;
  cpu_request: number; memory_request: number; cpu_pct: number; mem_pct: number; mem_mb: number;
  restarts: number; uptime_s: number; created_at: string;
}
export async function getPods(): Promise<PodInfo[]> {
  const { data } = await api.get<PodInfo[]>('/pods');
  return data;
}
export async function getPodLogs(workspaceId: number): Promise<{ pod_name: string; lines: string[] }> {
  const { data } = await api.get<{ pod_name: string; lines: string[] }>(`/pods/${workspaceId}/logs`);
  return data;
}

export async function uploadFiles(workspaceId: number, files: FileList | File[], dest = ''): Promise<string[]> {
  const form = new FormData();
  Array.from(files).forEach((f) => form.append('files', f));
  if (dest) form.append('dest', dest);
  const { data } = await api.post<{ uploaded: string[] }>(`/workspaces/${workspaceId}/upload`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data.uploaded;
}

export default api;

// ── GitHub integration ────────────────────────────────────────────────────────

export interface GitHubRepo {
  id:               number;
  name:             string;
  full_name:        string;
  private:          boolean;
  description?:     string | null;
  default_branch:   string;
  clone_url:        string;
  html_url:         string;
  updated_at?:      string | null;
  language?:        string | null;
  stargazers_count: number;
  forks_count:      number;
}

export interface GitHubBranch {
  name: string;
  sha:  string;
}

export interface GitHubStatus {
  connected:    boolean;
  github_login: string | null;
  avatar_url?:  string | null;
}

export async function getGitHubStatus(): Promise<GitHubStatus> {
  const { data } = await api.get<GitHubStatus>('/github/status');
  return data;
}

export async function disconnectGitHub(): Promise<void> {
  await api.delete('/github/disconnect');
}

export async function listGitHubRepos(page = 1, perPage = 50): Promise<GitHubRepo[]> {
  const { data } = await api.get<{ repos: GitHubRepo[]; page: number; total: number }>(
    `/github/repos?page=${page}&per_page=${perPage}`,
  );
  return data.repos;
}

export async function listGitHubBranches(owner: string, repo: string): Promise<GitHubBranch[]> {
  const { data } = await api.get<{ branches: GitHubBranch[] }>(
    `/github/repos/${owner}/${repo}/branches`,
  );
  return data.branches;
}

export async function createGitHubBranch(
  owner: string, repo: string, newBranch: string, fromBranch: string,
): Promise<GitHubBranch> {
  const { data } = await api.post<GitHubBranch>(
    `/github/repos/${owner}/${repo}/branches`,
    { owner, repo, new_branch: newBranch, from_branch: fromBranch },
  );
  return data;
}

export async function cloneRepoToWorkspace(
  workspaceId: number, owner: string, repo: string, branch?: string,
): Promise<{ ok: boolean; detail: string; file_count: number; repo: string }> {
  const { data } = await api.post('/github/clone', { workspace_id: workspaceId, owner, repo, branch });
  return data;
}

export async function commitAndPush(
  owner: string, repo: string, branch: string,
  path: string, content: string, message: string,
): Promise<{ ok: boolean; commit_sha: string; html_url: string }> {
  const { data } = await api.post('/github/commit', { owner, repo, branch, path, content, message });
  return data;
}
