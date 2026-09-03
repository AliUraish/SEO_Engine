from __future__ import annotations

from app.agents.auditor import AuditorAgent
from app.agents.base import Agent
from app.agents.crawler import CrawlerAgent
from app.agents.fixer import FixerAgent
from app.agents.keyword_scout import KeywordScoutAgent
from app.agents.migration_advisor import MigrationAdvisorAgent
from app.agents.publisher import PublisherAgent
from app.agents.ranker import RankerAgent
from app.agents.verifier import VerifierAgent

AGENTS: list[Agent] = [
    CrawlerAgent(),
    AuditorAgent(),
    KeywordScoutAgent(),
    FixerAgent(),
    PublisherAgent(),
    VerifierAgent(),
    RankerAgent(),
    MigrationAdvisorAgent(),
]

BY_JOB_TYPE: dict[str, Agent] = {t: a for a in AGENTS for t in a.handles}


def agent_for(job_type: str) -> Agent:
    try:
        return BY_JOB_TYPE[job_type]
    except KeyError as err:
        raise RuntimeError(f"No agent handles job type {job_type!r}") from err


def describe() -> list[dict[str, object]]:
    """For the dashboard's 'who does what' panel."""
    seen: dict[str, list[str]] = {}
    for a in AGENTS:
        seen.setdefault(a.name, []).extend(a.handles)
    return [{"name": n, "handles": h} for n, h in seen.items()]
