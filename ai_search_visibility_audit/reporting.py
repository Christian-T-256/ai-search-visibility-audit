"""Human-readable audit reports."""

from __future__ import annotations

from .models import AuditResult


def render_report(result: AuditResult) -> str:
    lines = [
        "AI Search Visibility Audit",
        f"Site: {result.url}",
        f"Score: {result.score}/100 (Grade {result.grade})",
        f"Signals: {sum(signal.passed for signal in result.signals)}/{len(result.signals)} passed",
        "",
        "Prioritized fixes:",
    ]
    if not result.fixes:
        lines.append("  None. All technical signals passed.")
    else:
        for index, signal in enumerate(result.fixes, start=1):
            lines.append(f"  {index}. [{signal.weight} pts] {signal.fix}")
            lines.append(f"     Evidence: {signal.evidence}")
    passing = [signal for signal in result.signals if signal.passed]
    lines.extend(["", "Passing signals:"])
    for signal in passing:
        lines.append(f"  PASS [{signal.weight} pts] {signal.label}")
    return "\n".join(lines) + "\n"

