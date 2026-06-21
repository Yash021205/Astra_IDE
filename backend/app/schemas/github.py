"""Pydantic schemas for GitHub integration endpoints."""
from typing import Optional
from pydantic import BaseModel, Field


class GitHubRepo(BaseModel):
    id:               int
    name:             str
    full_name:        str
    private:          bool
    description:      Optional[str] = None
    default_branch:   str = "main"
    clone_url:        str
    html_url:         str
    updated_at:       Optional[str] = None
    language:         Optional[str] = None
    stargazers_count: int = 0
    forks_count:      int = 0


class GitHubBranch(BaseModel):
    name: str
    sha:  str


class GitHubStatus(BaseModel):
    connected:    bool
    github_login: Optional[str] = None
    avatar_url:   Optional[str] = None


class RepoListResponse(BaseModel):
    repos: list[GitHubRepo]
    page:  int
    total: int


class BranchListResponse(BaseModel):
    branches: list[GitHubBranch]


class CreateBranchRequest(BaseModel):
    owner:       str = Field(min_length=1, max_length=128)
    repo:        str = Field(min_length=1, max_length=128)
    new_branch:  str = Field(min_length=1, max_length=255)
    from_branch: str = Field(default="main", min_length=1, max_length=255)


class CloneRepoRequest(BaseModel):
    workspace_id: int
    owner:        str = Field(min_length=1, max_length=128)
    repo:         str = Field(min_length=1, max_length=128)
    branch:       Optional[str] = None  # defaults to repo's default_branch


class CommitRequest(BaseModel):
    owner:   str    = Field(min_length=1, max_length=128)
    repo:    str    = Field(min_length=1, max_length=128)
    branch:  str    = Field(min_length=1, max_length=255)
    path:    str    = Field(min_length=1, max_length=500)
    content: str    = Field(max_length=1_000_000)
    message: str    = Field(min_length=1, max_length=500)


class CommitResponse(BaseModel):
    ok:         bool
    commit_sha: str
    html_url:   str
