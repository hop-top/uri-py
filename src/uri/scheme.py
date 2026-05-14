from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlparse


@dataclass(frozen=True)
class URI:
    scheme: str
    namespace: str
    id: str
    query: str = ""
    fragment: str = ""
    original: str = ""
    action: str = ""

    def canonical(self) -> str:
        out = f"{self.scheme}://{self.namespace}/{self.id}"
        if self.query:
            out += f"?{self.query}"
        if self.fragment:
            out += f"#{self.fragment}"
        return out

    def vanity(self) -> str:
        return self.original or self.canonical()

    def __str__(self) -> str:
        return self.canonical()


@dataclass(frozen=True)
class VanityAlias:
    from_: str = ""
    to: str = ""
    prefix: bool = False
    preserve_suffix: bool = False

    @classmethod
    def from_mapping(cls, value: dict[str, object]) -> "VanityAlias":
        return cls(
            from_=str(value.get("from", "")),
            to=str(value.get("to", "")),
            prefix=bool(value.get("prefix", False)),
            preserve_suffix=bool(value.get("preserveSuffix", value.get("preserve_suffix", False))),
        )


@dataclass(frozen=True)
class ActionRoute:
    command: str
    args: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, value: dict[str, object]) -> "ActionRoute":
        args = value.get("args", [])
        return cls(command=str(value.get("command", "")), args=[str(arg) for arg in args])


@dataclass(frozen=True)
class ResolvedAction:
    action: str
    command: str
    args: list[str]


@dataclass(frozen=True)
class ParseOptions:
    strict: bool = False
    json_ambiguity: bool = False

    @classmethod
    def from_mapping(cls, value: dict[str, object] | None) -> "ParseOptions":
        if value is None:
            return cls()
        return cls(
            strict=bool(value.get("strict", False)),
            json_ambiguity=bool(value.get("jsonAmbiguity", value.get("json_ambiguity", False))),
        )


@dataclass
class Policy:
    default_namespace_segments: int = 1
    scheme_namespace_segments: dict[str, int] = field(default_factory=dict)
    vanity_aliases: list[VanityAlias] = field(default_factory=list)
    action_routes: dict[str, ActionRoute] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: dict[str, object] | None) -> "Policy":
        if value is None:
            return default_policy()
        scheme_segments = value.get("schemeNamespaceSegments", value.get("scheme_namespace_segments", {}))
        aliases = value.get("vanityAliases", value.get("vanity_aliases", []))
        routes = value.get("actionRoutes", value.get("action_routes", {}))
        return cls(
            default_namespace_segments=int(value.get("defaultNamespaceSegments", value.get("default_namespace_segments", 1))),
            scheme_namespace_segments={str(k): int(v) for k, v in dict(scheme_segments).items()},
            vanity_aliases=[alias if isinstance(alias, VanityAlias) else VanityAlias.from_mapping(alias) for alias in aliases],
            action_routes={
                str(k): route if isinstance(route, ActionRoute) else ActionRoute.from_mapping(route)
                for k, route in dict(routes).items()
            },
        )

    def namespace_segments(self, scheme: str) -> int:
        return self.scheme_namespace_segments.get(scheme, self.default_namespace_segments or 1)

    def resolve_action(self, uri: URI) -> ResolvedAction:
        if uri is None:
            raise ValueError("uri: nil URI")
        if not uri.action:
            raise ValueError("uri: action is required")
        route = self.action_routes.get(uri.action)
        if route is None:
            raise ValueError(f"uri: unknown action {uri.action!r}")
        if not route.command:
            raise ValueError("uri: action route command is required")
        return ResolvedAction(
            action=uri.action,
            command=_expand_action_template(route.command, uri),
            args=[_expand_action_template(arg, uri) for arg in route.args],
        )

    def vanity_candidates(self, input: str) -> list["VanityCandidate"]:
        candidates = []
        for alias in self.vanity_aliases:
            distance = _levenshtein(input, alias.from_)
            if _within_fuzzy_threshold(input, alias.from_, distance):
                candidates.append(VanityCandidate(from_=alias.from_, to=alias.to, distance=distance))
        candidates.sort(key=lambda candidate: (candidate.distance, candidate.from_))
        return candidates

    def resolve_vanity(self, input: str, options: ParseOptions) -> tuple[str, str]:
        best: VanityAlias | None = None
        best_len = -1
        for alias in self.vanity_aliases:
            if not alias.from_ or not alias.to:
                raise ValueError("uri: vanity alias from and to are required")
            matched = input == alias.from_
            if not matched and alias.prefix:
                matched = input.startswith(alias.from_ + "/")
            if matched and len(alias.from_) > best_len:
                best = alias
                best_len = len(alias.from_)

        if best is None:
            if not options.strict:
                resolved = self._closest_vanity(input, options)
                if resolved is not None:
                    return resolved
            return input, ""

        target = best.to
        if best.prefix and best.preserve_suffix and len(input) > len(best.from_):
            target = target.rstrip("/") + input[len(best.from_) :]
        return target, input

    def _closest_vanity(self, input: str, options: ParseOptions) -> tuple[str, str] | None:
        candidates = self.vanity_candidates(input)
        if not candidates:
            return None
        best_distance = candidates[0].distance
        best = [candidate for candidate in candidates if candidate.distance == best_distance]
        if len(best) > 1:
            raise AmbiguousVanityError(input=input, candidates=best, as_json=options.json_ambiguity)
        return best[0].to, input


@dataclass(frozen=True)
class VanityCandidate:
    from_: str
    to: str
    distance: int

    def to_json(self) -> dict[str, object]:
        return {"from": self.from_, "to": self.to, "distance": self.distance}


class AmbiguousVanityError(ValueError):
    def __init__(self, input: str, candidates: list[VanityCandidate], as_json: bool = False) -> None:
        self.input = input
        self.candidates = candidates
        self.as_json = as_json
        super().__init__(self._message())

    def _message(self) -> str:
        if self.as_json:
            return json.dumps(
                {"input": self.input, "candidates": [candidate.to_json() for candidate in self.candidates]},
                separators=(",", ":"),
            )
        choices = ", ".join(candidate.from_ for candidate in self.candidates)
        return f"uri: ambiguous vanity alias {self.input!r}: {choices}"

    def to_json(self) -> dict[str, object]:
        return {"input": self.input, "candidates": [candidate.to_json() for candidate in self.candidates]}


def default_policy() -> Policy:
    return Policy(
        default_namespace_segments=1,
        scheme_namespace_segments={
            "task": 2,
            "doc": 2,
            "repo": 1,
            "tlc": 2,
            "task-dev": 2,
            "task-stress": 2,
        },
    )


DefaultPolicy = default_policy()


def parse(input: str, policy: Policy | dict[str, object] | None = None, options: ParseOptions | dict[str, object] | None = None) -> URI:
    parsed_policy = policy if isinstance(policy, Policy) else Policy.from_mapping(policy)
    parsed_options = options if isinstance(options, ParseOptions) else ParseOptions.from_mapping(options)
    if input == "":
        raise ValueError("uri: empty input")

    parse_input, vanity = parsed_policy.resolve_vanity(input, parsed_options)
    parsed = urlparse(parse_input)
    if not parsed.scheme:
        raise ValueError("uri: scheme is required")
    if not parsed.netloc:
        raise ValueError("uri: namespace is required")

    segments = [parsed.netloc]
    for segment in parsed.path.lstrip("/").split("/"):
        if segment:
            segments.append(unquote(segment))

    namespace_segments = parsed_policy.namespace_segments(parsed.scheme)
    if namespace_segments <= 0:
        raise ValueError("uri: namespace segment count must be positive")
    if len(segments) <= namespace_segments:
        raise ValueError("uri: id is required")

    namespace = "/".join(segments[:namespace_segments])
    id_ = "/".join(segments[namespace_segments:])
    if not namespace:
        raise ValueError("uri: namespace is required")
    if not id_:
        raise ValueError("uri: id is required")

    action = _action_from_query(parsed.query)
    return URI(
        scheme=parsed.scheme,
        namespace=namespace,
        id=id_,
        query=parsed.query,
        fragment=parsed.fragment,
        original=vanity,
        action=action,
    )

def resolve_action(uri: URI, policy: Policy | dict[str, object]) -> ResolvedAction:
    parsed_policy = policy if isinstance(policy, Policy) else Policy.from_mapping(policy)
    return parsed_policy.resolve_action(uri)


def _action_from_query(raw_query: str) -> str:
    values = parse_qs(raw_query, keep_blank_values=True)
    get = lambda key: values.get(key, [""])[0]
    candidates = []

    action = get("action")
    if action and not get("name"):
        candidates.append(action)

    cmd = get("cmd")
    verb = get("verb")
    if cmd or verb:
        if not cmd or not verb:
            raise ValueError("uri: cmd and verb must be provided together")
        candidates.append(f"{cmd}.{verb}")

    name = get("name")
    named_action = get("action")
    if name:
        if not named_action:
            raise ValueError("uri: name and action must be provided together")
        candidates.append(f"{name}.{named_action}")

    if not candidates:
        return ""
    if any(candidate != candidates[0] for candidate in candidates[1:]):
        raise ValueError("uri: conflicting action query parameters")
    return candidates[0]


def _expand_action_template(value: str, uri: URI) -> str:
    replacements = {
        "{scheme}": uri.scheme,
        "{namespace}": uri.namespace,
        "{id}": uri.id,
        "{query}": uri.query,
        "{fragment}": uri.fragment,
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value


def _within_fuzzy_threshold(input: str, candidate: str, distance: int) -> bool:
    threshold = max(len(input), len(candidate)) // 5
    threshold = max(2, min(8, threshold))
    return distance <= threshold


def _levenshtein(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ac in enumerate(a, start=1):
        current = [i]
        for j, bc in enumerate(b, start=1):
            cost = 0 if ac == bc else 1
            current.append(min(current[j - 1] + 1, previous[j] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]
