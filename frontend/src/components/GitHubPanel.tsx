'use client';
/**
 * GitHubPanel — Sidebar panel for GitHub integration.
 *
 * Sections:
 *  1. Account — connect / disconnect GitHub
 *  2. Repositories — searchable list of user repos (public + private)
 *  3. Git Ops — branch picker, commit & push (when a workspace context is provided)
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Github, Link2, Link2Off, RefreshCw, Search, Lock, Unlock,
  Star, GitFork, GitBranch, Plus, Upload, Check, ChevronDown,
  Loader2, AlertCircle, ExternalLink, FolderDown,
} from 'lucide-react';

import {
  listGitHubRepos, listGitHubBranches, createGitHubBranch,
  cloneRepoToWorkspace, commitAndPush, disconnectGitHub,
  type GitHubRepo, type GitHubBranch,
} from '../lib/api';
import { useAuth } from '../lib/auth';
import { toast } from '../lib/toast';
import { cn } from '../lib/utils';

// ── Helpers ──────────────────────────────────────────────────────────────────

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(d / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function GitHubIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
    </svg>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

interface GitHubPanelProps {
  /** Active workspace ID for Git operations. If undefined, only account/repos shown. */
  workspaceId?: number;
}

type PanelTab = 'repos' | 'gitops';

export default function GitHubPanel({ workspaceId }: GitHubPanelProps) {
  const { user, setUser } = useAuth();
  const isConnected = !!user?.github_login;

  const [tab, setTab]           = useState<PanelTab>('repos');
  const [repos, setRepos]       = useState<GitHubRepo[]>([]);
  const [repoFilter, setFilter] = useState('');
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [reposError, setReposError]     = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);

  // Git Ops state
  const [selectedRepo, setSelectedRepo] = useState<GitHubRepo | null>(null);
  const [branches, setBranches]         = useState<GitHubBranch[]>([]);
  const [activeBranch, setActiveBranch] = useState('');
  const [branchDropdown, setBranchDropdown] = useState(false);
  const [newBranchName, setNewBranchName]   = useState('');
  const [creatingBranch, setCreatingBranch] = useState(false);
  const [showNewBranch, setShowNewBranch]   = useState(false);

  // Commit state
  const [commitPath, setCommitPath]     = useState('');
  const [commitContent, setCommitContent] = useState('');
  const [commitMsg, setCommitMsg]       = useState('');
  const [committing, setCommitting]     = useState(false);

  // Clone state
  const [cloningRepo, setCloningRepo]   = useState<string | null>(null);

  // Load repos when connected
  const fetchRepos = useCallback(async () => {
    if (!isConnected) return;
    setLoadingRepos(true);
    setReposError(null);
    try {
      const data = await listGitHubRepos();
      setRepos(data);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Failed to load repos';
      if (detail === 'github_not_connected') {
        setReposError('GitHub account disconnected. Please reconnect.');
      } else {
        setReposError(detail);
      }
    } finally {
      setLoadingRepos(false);
    }
  }, [isConnected]);

  useEffect(() => { fetchRepos(); }, [fetchRepos]);

  // Load branches when a repo is selected for Git Ops
  const loadBranches = useCallback(async (repo: GitHubRepo) => {
    setSelectedRepo(repo);
    setActiveBranch(repo.default_branch);
    setBranches([]);
    try {
      const data = await listGitHubBranches(
        repo.full_name.split('/')[0],
        repo.name,
      );
      setBranches(data);
    } catch { /* non-fatal */ }
  }, []);

  async function handleDisconnect() {
    if (!confirm('Disconnect your GitHub account? You can reconnect any time.')) return;
    setDisconnecting(true);
    try {
      await disconnectGitHub();
      // Optimistically update the local user state
      setUser({ ...user!, github_login: null });
      setRepos([]);
      toast.success('GitHub disconnected');
    } catch (err: any) {
      toast.error('Failed to disconnect', err?.message);
    } finally {
      setDisconnecting(false);
    }
  }

  async function handleClone(repo: GitHubRepo) {
    if (!workspaceId) {
      toast.error('No workspace selected', 'Open a workspace first');
      return;
    }
    const [owner] = repo.full_name.split('/');
    setCloningRepo(repo.full_name);
    try {
      const res = await cloneRepoToWorkspace(workspaceId, owner, repo.name, repo.default_branch);
      toast.success(`Cloned ${repo.name}`, `${res.file_count} files imported`);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Clone failed';
      toast.error('Clone failed', detail);
    } finally {
      setCloningRepo(null);
    }
  }

  async function handleCreateBranch() {
    if (!selectedRepo || !newBranchName.trim()) return;
    const [owner] = selectedRepo.full_name.split('/');
    setCreatingBranch(true);
    try {
      const b = await createGitHubBranch(owner, selectedRepo.name, newBranchName.trim(), activeBranch);
      setBranches((prev) => [...prev, b]);
      setActiveBranch(b.name);
      setNewBranchName('');
      setShowNewBranch(false);
      toast.success(`Branch "${b.name}" created`);
    } catch (err: any) {
      toast.error('Create branch failed', err?.response?.data?.detail || err?.message);
    } finally {
      setCreatingBranch(false);
    }
  }

  async function handleCommit() {
    if (!selectedRepo || !commitPath || !commitMsg) return;
    const [owner] = selectedRepo.full_name.split('/');
    setCommitting(true);
    try {
      const res = await commitAndPush(owner, selectedRepo.name, activeBranch, commitPath, commitContent, commitMsg);
      toast.success('Pushed!', `Commit ${res.commit_sha.slice(0, 7)}`);
      setCommitMsg('');
    } catch (err: any) {
      toast.error('Commit failed', err?.response?.data?.detail || err?.message);
    } finally {
      setCommitting(false);
    }
  }

  const filteredRepos = repos.filter((r) =>
    r.full_name.toLowerCase().includes(repoFilter.toLowerCase())
  );

  // ── Not connected ─────────────────────────────────────────────────────────
  if (!isConnected) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 p-6 text-center h-full">
        <div className="w-14 h-14 rounded-2xl bg-zinc-900 dark:bg-white/5 flex items-center justify-center border border-edge">
          <GitHubIcon size={28} />
        </div>
        <div>
          <p className="text-sm font-semibold text-ink">Connect GitHub</p>
          <p className="text-xs text-muted mt-1 leading-relaxed max-w-[200px]">
            Link your account to access private repos and push from the IDE.
          </p>
        </div>
        <a
          href="/api/auth/github/login"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                     bg-zinc-900 dark:bg-white text-white dark:text-zinc-900
                     hover:bg-zinc-700 dark:hover:bg-zinc-100 transition-colors"
        >
          <GitHubIcon size={14} />
          Connect GitHub
        </a>
      </div>
    );
  }

  // ── Connected ─────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full min-h-0 text-sm">
      {/* Account header */}
      <div className="px-3 py-2.5 border-b border-edge bg-raised/40 shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-zinc-800 dark:bg-white/10 flex items-center justify-center shrink-0">
            <GitHubIcon size={14} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold truncate text-ink">{user?.github_login}</p>
            <p className="text-[10px] text-emerald-500 dark:text-emerald-400 flex items-center gap-1">
              <Link2 size={9} /> Connected
            </p>
          </div>
          <button
            type="button"
            onClick={handleDisconnect}
            disabled={disconnecting}
            title="Disconnect GitHub"
            className="btn-ghost p-1 text-muted hover:text-rose-500 dark:hover:text-rose-400"
          >
            {disconnecting ? <Loader2 size={13} className="animate-spin" /> : <Link2Off size={13} />}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-edge shrink-0">
        {(['repos', 'gitops'] as PanelTab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={cn(
              'flex-1 py-1.5 text-[11px] font-medium transition-colors',
              tab === t
                ? 'text-astra-600 dark:text-astra-400 border-b-2 border-astra-500 -mb-px'
                : 'text-muted hover:text-ink',
            )}
          >
            {t === 'repos' ? 'Repositories' : 'Git Ops'}
          </button>
        ))}
      </div>

      {/* ── REPOS TAB ── */}
      {tab === 'repos' && (
        <div className="flex flex-col flex-1 min-h-0">
          {/* Search + refresh */}
          <div className="flex gap-1.5 px-2 py-2 shrink-0">
            <div className="flex-1 relative">
              <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted pointer-events-none" />
              <input
                type="search"
                placeholder="Filter repos…"
                value={repoFilter}
                onChange={(e) => setFilter(e.target.value)}
                className="input-base py-1 pl-6 text-xs w-full"
              />
            </div>
            <button type="button" onClick={fetchRepos} disabled={loadingRepos}
              className="btn-ghost p-1.5 shrink-0" title="Refresh">
              <RefreshCw size={13} className={cn(loadingRepos && 'animate-spin')} />
            </button>
          </div>

          {/* Error */}
          {reposError && (
            <div className="mx-2 mb-2 px-2 py-1.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 text-xs flex gap-1.5">
              <AlertCircle size={12} className="shrink-0 mt-0.5" />
              {reposError}
            </div>
          )}

          {/* Loading skeleton */}
          {loadingRepos && repos.length === 0 && (
            <div className="px-3 space-y-2 py-2">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-12 rounded-lg bg-raised animate-pulse" />
              ))}
            </div>
          )}

          {/* Repo list */}
          <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
            {filteredRepos.map((repo) => {
              const isCloning = cloningRepo === repo.full_name;
              return (
                <div key={repo.id}
                  className="group rounded-lg border border-edge hover:border-astra-500/40 bg-surface hover:bg-raised
                             transition-all p-2.5 cursor-default"
                >
                  <div className="flex items-start gap-1.5">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-medium text-xs text-ink truncate">{repo.name}</span>
                        {repo.private
                          ? <span title="Private"><Lock size={10} className="text-amber-500 shrink-0" /></span>
                          : <span title="Public"><Unlock size={10} className="text-muted shrink-0" /></span>}
                        {repo.language && (
                          <span className="text-[10px] text-muted bg-raised px-1 rounded">{repo.language}</span>
                        )}
                      </div>
                      {repo.description && (
                        <p className="text-[11px] text-muted mt-0.5 line-clamp-1">{repo.description}</p>
                      )}
                      <div className="flex items-center gap-2 mt-1 text-[10px] text-faint">
                        <span className="flex items-center gap-0.5">
                          <Star size={9} /> {repo.stargazers_count}
                        </span>
                        <span className="flex items-center gap-0.5">
                          <GitFork size={9} /> {repo.forks_count}
                        </span>
                        <span className="flex items-center gap-0.5">
                          <GitBranch size={9} /> {repo.default_branch}
                        </span>
                        {repo.updated_at && <span>{timeAgo(repo.updated_at)}</span>}
                      </div>
                    </div>
                  </div>

                  {/* Actions row */}
                  <div className="flex gap-1 mt-2">
                    {workspaceId && (
                      <button type="button"
                        onClick={() => handleClone(repo)}
                        disabled={isCloning}
                        className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium
                                   bg-astra-600/10 text-astra-600 dark:text-astra-400 hover:bg-astra-600/20
                                   disabled:opacity-60 transition-colors"
                      >
                        {isCloning
                          ? <Loader2 size={9} className="animate-spin" />
                          : <FolderDown size={9} />}
                        {isCloning ? 'Cloning…' : 'Open in workspace'}
                      </button>
                    )}
                    <button type="button"
                      onClick={() => { setSelectedRepo(repo); setTab('gitops'); loadBranches(repo); }}
                      className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium
                                 bg-raised text-muted hover:text-ink transition-colors"
                    >
                      <GitBranch size={9} /> Git Ops
                    </button>
                    <a href={repo.html_url} target="_blank" rel="noopener noreferrer"
                      className="ml-auto flex items-center gap-1 px-2 py-0.5 rounded text-[10px]
                                 text-muted hover:text-ink transition-colors"
                    >
                      <ExternalLink size={9} />
                    </a>
                  </div>
                </div>
              );
            })}

            {!loadingRepos && filteredRepos.length === 0 && !reposError && (
              <p className="text-xs text-muted text-center py-6">
                {repoFilter ? 'No repos match your search.' : 'No repositories found.'}
              </p>
            )}
          </div>
        </div>
      )}

      {/* ── GIT OPS TAB ── */}
      {tab === 'gitops' && (
        <div className="flex flex-col flex-1 min-h-0 overflow-y-auto p-3 gap-4">
          {/* Repo selector */}
          <div>
            <label className="block text-[10px] font-medium text-muted mb-1">Repository</label>
            <select
              value={selectedRepo?.full_name || ''}
              onChange={(e) => {
                const r = repos.find((x) => x.full_name === e.target.value);
                if (r) loadBranches(r);
              }}
              className="input-base text-xs w-full"
            >
              <option value="">— select a repo —</option>
              {repos.map((r) => (
                <option key={r.id} value={r.full_name}>{r.full_name}</option>
              ))}
            </select>
          </div>

          {selectedRepo && (
            <>
              {/* Branch selector */}
              <div>
                <label className="block text-[10px] font-medium text-muted mb-1">Branch</label>
                <div className="relative">
                  <button type="button"
                    onClick={() => setBranchDropdown((v) => !v)}
                    className="input-base text-xs w-full flex items-center justify-between"
                  >
                    <span className="flex items-center gap-1.5">
                      <GitBranch size={11} className="text-muted" />
                      {activeBranch || 'Select branch'}
                    </span>
                    <ChevronDown size={11} className="text-muted" />
                  </button>
                  <AnimatePresence>
                    {branchDropdown && (
                      <motion.div
                        initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
                        className="absolute z-20 mt-1 w-full rounded-lg border border-edge bg-surface shadow-pop p-1 max-h-40 overflow-y-auto"
                      >
                        {branches.map((b) => (
                          <button key={b.name} type="button"
                            onClick={() => { setActiveBranch(b.name); setBranchDropdown(false); }}
                            className={cn(
                              'w-full text-left px-2.5 py-1.5 rounded text-xs flex items-center gap-1.5 hover:bg-raised',
                              b.name === activeBranch && 'text-astra-600 dark:text-astra-400 font-medium',
                            )}
                          >
                            <GitBranch size={10} />
                            {b.name}
                            {b.name === activeBranch && <Check size={10} className="ml-auto" />}
                          </button>
                        ))}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>

                {/* New branch */}
                {!showNewBranch ? (
                  <button type="button" onClick={() => setShowNewBranch(true)}
                    className="mt-1 flex items-center gap-1 text-[10px] text-muted hover:text-ink transition-colors">
                    <Plus size={10} /> New branch from {activeBranch}
                  </button>
                ) : (
                  <div className="mt-2 flex gap-1">
                    <input
                      type="text"
                      placeholder="new-branch-name"
                      value={newBranchName}
                      onChange={(e) => setNewBranchName(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleCreateBranch()}
                      className="input-base text-xs flex-1"
                      autoFocus
                    />
                    <button type="button" onClick={handleCreateBranch} disabled={creatingBranch || !newBranchName.trim()}
                      className="btn-primary px-2.5 text-xs disabled:opacity-60">
                      {creatingBranch ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
                    </button>
                    <button type="button" onClick={() => { setShowNewBranch(false); setNewBranchName(''); }}
                      className="btn-ghost px-2 text-xs">✕</button>
                  </div>
                )}
              </div>

              {/* Commit & Push */}
              <div className="space-y-2 border-t border-edge pt-3">
                <p className="text-[10px] font-semibold text-muted uppercase tracking-wider">
                  Commit &amp; Push
                </p>
                <div>
                  <label className="block text-[10px] font-medium text-muted mb-1">File path</label>
                  <input type="text" placeholder="src/main.py"
                    value={commitPath} onChange={(e) => setCommitPath(e.target.value)}
                    className="input-base text-xs w-full" />
                </div>
                <div>
                  <label className="block text-[10px] font-medium text-muted mb-1">Content</label>
                  <textarea rows={6} placeholder="File content to push…"
                    value={commitContent} onChange={(e) => setCommitContent(e.target.value)}
                    className="input-base text-xs w-full resize-y font-mono" />
                </div>
                <div>
                  <label className="block text-[10px] font-medium text-muted mb-1">Commit message</label>
                  <input type="text" placeholder="feat: update main.py"
                    value={commitMsg} onChange={(e) => setCommitMsg(e.target.value)}
                    className="input-base text-xs w-full" />
                </div>
                <button type="button" onClick={handleCommit}
                  disabled={committing || !commitPath || !commitMsg}
                  className="btn-primary w-full py-2 text-xs disabled:opacity-60 flex items-center justify-center gap-1.5"
                >
                  {committing
                    ? <><Loader2 size={12} className="animate-spin" /> Pushing…</>
                    : <><Upload size={12} /> Commit &amp; Push to {activeBranch}</>}
                </button>
              </div>
            </>
          )}

          {!selectedRepo && (
            <p className="text-xs text-muted text-center py-6">
              Select a repository above to use Git operations.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
