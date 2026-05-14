from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .scheme import Policy, URI, default_policy, parse

Parser = Callable[[str], URI]
Completer = Callable[[str], list[str]]


@dataclass(frozen=True)
class TypeRegistration:
    name: str
    parser: Optional[Parser] = None
    completer: Optional[Completer] = None


class Registry:
    def __init__(self, policy: Policy | None = None) -> None:
        self._types: dict[str, TypeRegistration] = {}
        self._policy = policy or default_policy()

    def register(self, reg: TypeRegistration) -> None:
        if not reg.name:
            raise ValueError("uri: registration name is required")
        if reg.name in self._types:
            raise ValueError(f"uri: type {reg.name!r} already registered")
        self._types[reg.name] = reg

    def parse(self, input: str) -> URI:
        parsed = parse(input, self._policy)
        reg = self._types.get(parsed.scheme)
        if reg is None:
            raise ValueError(f"uri: unknown type {parsed.scheme!r}")
        if reg.parser is not None:
            return reg.parser(input)
        return parsed

    def complete_vanity(self, input: str):
        return self._policy.vanity_candidates(input)

    def complete(self, type_name: str, prefix: str) -> list[str] | None:
        reg = self._types.get(type_name)
        if reg is None:
            raise ValueError(f"uri: unknown type {type_name!r}")
        if reg.completer is None:
            return None
        return reg.completer(prefix)

    def types(self) -> list[str]:
        return sorted(self._types)


def new_registry() -> Registry:
    return Registry()


def new_registry_with_policy(policy: Policy) -> Registry:
    return Registry(policy)
