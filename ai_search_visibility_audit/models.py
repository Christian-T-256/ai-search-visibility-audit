"""Shared models for audits, site profiles, and generated artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class FetchResponse:
    """A small transport-neutral HTTP response."""

    url: str
    status: int
    text: str
    content_type: str = "text/plain"

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 400


@dataclass(frozen=True)
class SignalResult:
    """The outcome of one weighted audit signal."""

    key: str
    label: str
    weight: int
    passed: bool
    evidence: str
    fix: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuditResult:
    """Complete, JSON-serializable audit result."""

    url: str
    score: int
    grade: str
    earned_points: int
    total_points: int
    schema_types: tuple[str, ...]
    signals: tuple[SignalResult, ...]

    @property
    def fixes(self) -> tuple[SignalResult, ...]:
        return tuple(
            sorted(
                (signal for signal in self.signals if not signal.passed),
                key=lambda signal: (-signal.weight, signal.key),
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "score": self.score,
            "grade": self.grade,
            "earned_points": self.earned_points,
            "total_points": self.total_points,
            "schema_types": list(self.schema_types),
            "signals": [signal.to_dict() for signal in self.signals],
            "prioritized_fixes": [signal.to_dict() for signal in self.fixes],
        }


@dataclass(frozen=True)
class PageLink:
    title: str
    path: str
    description: str


@dataclass(frozen=True)
class FAQ:
    question: str
    answer: str


@dataclass(frozen=True)
class SiteProfile:
    """Validated inputs used to generate llms.txt and JSON-LD."""

    brand: str
    tagline: str
    url: str
    audience: str
    services: tuple[str, ...]
    pages: tuple[PageLink, ...] = field(default_factory=tuple)
    ignore_paths: tuple[str, ...] = field(default_factory=tuple)
    faqs: tuple[FAQ, ...] = field(default_factory=tuple)

