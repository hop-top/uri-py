from __future__ import annotations

from dataclasses import dataclass

from .registry import Registry


@dataclass(frozen=True)
class CompletionResult:
    suggestions: list[str]


def complete_with_scheme(reg: Registry, type_name: str, to_complete: str) -> CompletionResult:
    prefix = to_complete
    scheme = ""

    idx = to_complete.find("://")
    if idx >= 0:
        scheme = to_complete[:idx]
        prefix = to_complete[idx + 3 :]

    if scheme:
        candidates = reg.complete_vanity(to_complete)
        if len(candidates) > 1:
            return CompletionResult(suggestions=[f"{candidate.from_}\tcanonical: {candidate.to}" for candidate in candidates])

    suggestions = reg.complete(type_name, prefix) or []
    if not scheme:
        return CompletionResult(suggestions=suggestions)

    return CompletionResult(suggestions=[f"{scheme}://{s}" for s in suggestions])
