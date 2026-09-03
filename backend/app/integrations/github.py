"""GitHub PR adapter (PyGithub, run in a thread so the event loop stays free)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

from github import Auth, Github

from app.config import assert_network, get_settings

log = logging.getLogger(__name__)


@dataclass
class PullRequestInfo:
    number: int
    url: str
    merged: bool
    merge_sha: str | None
    state: str  # open|closed


class GitHubClient(Protocol):
    enabled: bool

    async def open_pull_request(self, repo: str, base: str, head: str, title: str, body: str) -> PullRequestInfo: ...
    async def get_pull_request(self, repo: str, number: int) -> PullRequestInfo: ...


class PyGitHub:
    enabled = True

    def __init__(self, token: str) -> None:
        self._gh = Github(auth=Auth.Token(token), user_agent="RankOS/0.1")

    async def open_pull_request(self, repo: str, base: str, head: str, title: str, body: str) -> PullRequestInfo:
        assert_network("open a GitHub pull request")

        def _do() -> PullRequestInfo:
            pr = self._gh.get_repo(repo).create_pull(base=base, head=head, title=title, body=body)
            return PullRequestInfo(pr.number, pr.html_url, False, None, "open")

        return await asyncio.to_thread(_do)

    async def get_pull_request(self, repo: str, number: int) -> PullRequestInfo:
        assert_network("read a GitHub pull request")

        def _do() -> PullRequestInfo:
            pr = self._gh.get_repo(repo).get_pull(number)
            return PullRequestInfo(pr.number, pr.html_url, bool(pr.merged), pr.merge_commit_sha, pr.state)

        return await asyncio.to_thread(_do)


class NoopGitHub:
    enabled = False

    async def open_pull_request(self, repo: str, base: str, head: str, title: str, body: str) -> PullRequestInfo:
        raise RuntimeError("GitHub is not configured (set GITHUB_TOKEN and NETWORK_ENABLED=true)")

    async def get_pull_request(self, repo: str, number: int) -> PullRequestInfo:
        raise RuntimeError("GitHub is not configured")


def create_github() -> GitHubClient:
    s = get_settings()
    if s.github_token and s.network_enabled:
        log.info("github: enabled")
        return PyGitHub(s.github_token)
    log.info("github: disabled")
    return NoopGitHub()
