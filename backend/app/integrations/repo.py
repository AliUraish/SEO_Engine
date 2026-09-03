"""Local checkout of the site's repository. Edits happen on a branch; nothing touches the
network until `push()` (gated by NETWORK_ENABLED)."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from git import Repo

from app.config import assert_network, get_settings

log = logging.getLogger(__name__)

EDITABLE = {
    ".html",
    ".htm",
    ".tsx",
    ".jsx",
    ".ts",
    ".js",
    ".mjs",
    ".vue",
    ".svelte",
    ".astro",
    ".md",
    ".mdx",
    ".php",
    ".liquid",
    ".hbs",
    ".ejs",
    ".njk",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".py",
}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".nuxt", "out", "vendor", ".venv", "__pycache__"}


@dataclass
class ApplyResult:
    status: str  # applied|needs_manual
    file_path: str | None
    note: str


class LocalRepo(Protocol):
    enabled: bool
    root: str | None

    async def checkout_branch(self, branch: str, base: str) -> None: ...
    async def grep(self, needle: str, limit: int = 5) -> list[str]: ...
    async def replace_exact(self, before: str, after: str, hint_path: str | None = None) -> ApplyResult: ...
    async def commit(self, message: str) -> str: ...
    async def push(self, branch: str) -> None: ...


class GitLocalRepo:
    enabled = True

    def __init__(self, root: str) -> None:
        self.root = str(Path(root).resolve())
        self._repo = Repo(self.root)

    async def checkout_branch(self, branch: str, base: str) -> None:
        def _do() -> None:
            self._repo.git.checkout(base)
            if branch in [h.name for h in self._repo.heads]:
                self._repo.git.branch("-D", branch)
            self._repo.git.checkout("-b", branch)

        await asyncio.to_thread(_do)

    async def grep(self, needle: str, limit: int = 5) -> list[str]:
        def _do() -> list[str]:
            hits: list[str] = []
            for dirpath, dirnames, filenames in os.walk(self.root):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                for fn in filenames:
                    if Path(fn).suffix not in EDITABLE:
                        continue
                    full = Path(dirpath) / fn
                    try:
                        if full.stat().st_size > 2_000_000:
                            continue
                        if needle in full.read_text(encoding="utf-8", errors="ignore"):
                            hits.append(str(full.relative_to(self.root)))
                            if len(hits) >= limit:
                                return hits
                    except OSError:
                        continue
            return hits

        return await asyncio.to_thread(_do)

    async def replace_exact(self, before: str, after: str, hint_path: str | None = None) -> ApplyResult:
        """Replace an exact string in exactly one file; anything ambiguous becomes a manual task."""
        if not before:
            return ApplyResult("needs_manual", None, "No 'before' text to locate in source")
        candidates = [hint_path] if hint_path else await self.grep(before, 3)
        if not candidates:
            return ApplyResult("needs_manual", None, "Text not found in repo; it may come from a CMS or data file")
        if len(candidates) > 1:
            return ApplyResult("needs_manual", None, f"Text appears in {len(candidates)} files: {', '.join(candidates)}")
        rel = candidates[0]
        full = Path(self.root) / rel
        content = full.read_text(encoding="utf-8")
        n = content.count(before)
        if n != 1:
            return ApplyResult("needs_manual", rel, f"Text occurs {n} times in {rel}")
        full.write_text(content.replace(before, after, 1), encoding="utf-8")
        return ApplyResult("applied", rel, "Replaced in place")

    async def commit(self, message: str) -> str:
        def _do() -> str:
            self._repo.git.add("-A")
            self._repo.index.commit(message)
            return self._repo.head.commit.hexsha

        return await asyncio.to_thread(_do)

    async def push(self, branch: str) -> None:
        assert_network("push a branch to the remote")
        await asyncio.to_thread(lambda: self._repo.git.push("--set-upstream", "origin", branch))


class NoopLocalRepo:
    enabled = False
    root = None

    async def checkout_branch(self, branch: str, base: str) -> None:
        raise RuntimeError("Repo is not configured (set REPO_LOCAL_PATH)")

    async def grep(self, needle: str, limit: int = 5) -> list[str]:
        return []

    async def replace_exact(self, before: str, after: str, hint_path: str | None = None) -> ApplyResult:
        return ApplyResult("needs_manual", None, "Repo is not configured (set REPO_LOCAL_PATH)")

    async def commit(self, message: str) -> str:
        raise RuntimeError("Repo is not configured")

    async def push(self, branch: str) -> None:
        raise RuntimeError("Repo is not configured")


def create_local_repo() -> LocalRepo:
    s = get_settings()
    if s.repo_local_path:
        log.info("repo: enabled (%s)", s.repo_local_path)
        return GitLocalRepo(s.repo_local_path)
    log.info("repo: disabled")
    return NoopLocalRepo()
