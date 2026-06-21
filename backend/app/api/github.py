"""GitHub integration endpoints — repo listing, branch ops, clone, commit/push."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import httpx

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User, Workspace
from app.schemas.github import (
    BranchListResponse,
    CloneRepoRequest,
    CommitRequest,
    CommitResponse,
    CreateBranchRequest,
    GitHubBranch,
    GitHubStatus,
    RepoListResponse,
)
from app.services import github_service
from app.services import workspace_files
from app.services import sharing_service

router = APIRouter(prefix="/github", tags=["github"])


# ── Helpers ─────────────────────────────────────────────────────────────────

def _require_github_token(user: User) -> str:
    """Return the decrypted GitHub access token or raise 402."""
    if not user.github_access_token or not user.github_login:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="github_not_connected",
        )
    return github_service.decrypt_token(user.github_access_token)


def _github_error(exc: Exception) -> HTTPException:
    """Convert httpx errors to a clean 502."""
    if isinstance(exc, httpx.HTTPStatusError):
        detail = f"GitHub API error {exc.response.status_code}: {exc.response.text[:200]}"
    else:
        detail = f"GitHub API unreachable: {exc}"
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)


# ── Account status ───────────────────────────────────────────────────────────

@router.get("/status", response_model=GitHubStatus)
def get_github_status(current_user: User = Depends(get_current_user)) -> GitHubStatus:
    """Return the GitHub connection status for the current user."""
    return GitHubStatus(
        connected=current_user.github_login is not None,
        github_login=current_user.github_login,
        avatar_url=current_user.avatar_url,
    )


# ── Repositories ─────────────────────────────────────────────────────────────

@router.get("/repos", response_model=RepoListResponse)
def list_repos(
    page:     int = 1,
    per_page: int = 50,
    current_user: User = Depends(get_current_user),
) -> RepoListResponse:
    """List the authenticated user's GitHub repositories (public + private)."""
    token = _require_github_token(current_user)
    try:
        repos = github_service.get_user_repos(token, page=page, per_page=per_page)
    except (httpx.HTTPError, Exception) as exc:
        raise _github_error(exc)
    return RepoListResponse(repos=repos, page=page, total=len(repos))


# ── Branches ─────────────────────────────────────────────────────────────────

@router.get("/repos/{owner}/{repo}/branches", response_model=BranchListResponse)
def list_branches(
    owner: str,
    repo:  str,
    current_user: User = Depends(get_current_user),
) -> BranchListResponse:
    """List branches for a given repository."""
    token = _require_github_token(current_user)
    try:
        branches = github_service.get_repo_branches(token, owner, repo)
    except (httpx.HTTPError, Exception) as exc:
        raise _github_error(exc)
    return BranchListResponse(branches=[GitHubBranch(**b) for b in branches])


@router.post("/repos/{owner}/{repo}/branches", response_model=GitHubBranch, status_code=201)
def create_branch(
    owner:   str,
    repo:    str,
    payload: CreateBranchRequest,
    current_user: User = Depends(get_current_user),
) -> GitHubBranch:
    """Create a new branch from the HEAD of another branch."""
    token = _require_github_token(current_user)
    try:
        result = github_service.create_branch(
            token, owner, repo, payload.new_branch, payload.from_branch
        )
    except (httpx.HTTPError, Exception) as exc:
        raise _github_error(exc)
    return GitHubBranch(**result)


# ── Clone repo into workspace ─────────────────────────────────────────────────

@router.post("/clone")
def clone_repo(
    payload: CloneRepoRequest,
    db:      Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Clone a GitHub repository (public or private) into a workspace.
    The OAuth token is injected into the HTTPS clone URL so private repos work.
    """
    token = _require_github_token(current_user)

    # Verify the user can access this workspace
    if not sharing_service.user_can_access(db, payload.workspace_id, current_user.id):
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Build the authenticated clone URL
    clone_url = f"https://github.com/{payload.owner}/{payload.repo}.git"
    auth_url  = github_service.build_clone_url(token, clone_url)

    # Use the workspace_files import function (which does a git clone)
    result = workspace_files.import_repo(
        payload.workspace_id,
        auth_url,
        branch=payload.branch,
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.detail)

    return {
        "ok":         True,
        "detail":     result.detail,
        "file_count": result.file_count,
        "repo":       f"{payload.owner}/{payload.repo}",
    }


# ── Commit & Push ─────────────────────────────────────────────────────────────

@router.post("/commit", response_model=CommitResponse)
def commit_and_push(
    payload: CommitRequest,
    current_user: User = Depends(get_current_user),
) -> CommitResponse:
    """
    Commit a single file change to a GitHub repository and push it.
    The file content is the current version the user wants to publish.
    """
    token = _require_github_token(current_user)
    try:
        result = github_service.commit_file(
            access_token=token,
            owner=payload.owner,
            repo=payload.repo,
            path=payload.path,
            content=payload.content,
            branch=payload.branch,
            message=payload.message,
        )
    except (httpx.HTTPError, Exception) as exc:
        raise _github_error(exc)
    return CommitResponse(ok=True, **result)
