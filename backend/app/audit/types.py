from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.crawler.parse import PageSnapshot

Severity = Literal["critical", "high", "medium", "low", "info"]

SEVERITY_WEIGHT: dict[str, int] = {"critical": 25, "high": 12, "medium": 6, "low": 2, "info": 0}


@dataclass
class Finding:
    rule_code: str
    severity: Severity
    message: str
    fix_hint: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PageRuleContext:
    snapshot: PageSnapshot
    focus_keyword: str | None = None


@dataclass
class PageRule:
    code: str
    title: str
    category: str  # title|meta|headings|content|images|links|technical|keyword|social
    severity: Severity
    check: Callable[[PageRuleContext], Finding | None]
