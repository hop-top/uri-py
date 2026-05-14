from __future__ import annotations

import json
from pathlib import Path

import pytest

from uri import (
    ActionRoute,
    AmbiguousVanityError,
    HandlerSpec,
    ParseOptions,
    Policy,
    TypeRegistration,
    VanityAlias,
    complete_with_scheme,
    desktop_filename,
    new_registry,
    new_registry_with_policy,
    parse,
    resolve_action,
    snippet,
)

ROOT = Path(__file__).resolve().parents[2]


def load_uri_fixture() -> dict:
    with (ROOT / "spec/fixtures/uri-contract.json").open() as fh:
        return json.load(fh)


def load_handler_fixture() -> dict:
    with (ROOT / "spec/fixtures/handler-contract.json").open() as fh:
        return json.load(fh)


def policy_from_fixture(fixture: dict) -> Policy:
    namespace_policy = fixture["namespacePolicy"]
    return Policy(
        default_namespace_segments=namespace_policy["defaultNamespaceSegments"],
        scheme_namespace_segments=namespace_policy["schemeNamespaceSegments"],
    )


def assert_uri_matches(got, expected: dict, canonical: str) -> None:
    assert got.scheme == expected.get("scheme", "")
    assert got.namespace == expected.get("namespace", "")
    assert got.id == expected.get("id", "")
    if "query" in expected:
        assert got.query == expected["query"]
    if "fragment" in expected:
        assert got.fragment == expected["fragment"]
    if "original" in expected:
        assert got.original == expected["original"]
    if "action" in expected:
        assert got.action == expected["action"]
    assert got.canonical() == canonical
    assert str(got) == canonical


def test_parse_contract_valid_cases() -> None:
    fixture = load_uri_fixture()
    policy = policy_from_fixture(fixture)

    for case in fixture["validCases"]:
        got = parse(case["input"], policy=policy)
        assert_uri_matches(got, case["expected"], case["canonical"])


def test_parse_contract_invalid_cases() -> None:
    fixture = load_uri_fixture()
    policy = policy_from_fixture(fixture)

    for case in fixture["invalidCases"]:
        with pytest.raises(ValueError):
            parse(case["input"], policy=policy)


def test_parse_contract_vanity_cases() -> None:
    fixture = load_uri_fixture()
    base_policy = policy_from_fixture(fixture)

    for case in fixture["vanityCases"]:
        policy = Policy(
            default_namespace_segments=base_policy.default_namespace_segments,
            scheme_namespace_segments=base_policy.scheme_namespace_segments,
            vanity_aliases=[VanityAlias.from_mapping(alias) for alias in case.get("aliases", [])],
        )
        options = ParseOptions.from_mapping(case.get("options"))

        if not case["valid"]:
            with pytest.raises(ValueError):
                parse(case["input"], policy=policy, options=options)
            continue

        got = parse(case["input"], policy=policy, options=options)
        assert_uri_matches(got, case["expected"], case["canonical"])
        assert got.vanity() == case["expected"].get("original", case["canonical"])


def test_ambiguous_fuzzy_vanity_json_error() -> None:
    policy = Policy(
        default_namespace_segments=1,
        scheme_namespace_segments={"task": 2},
        vanity_aliases=[
            VanityAlias(from_="task://shortcuta", to="task://hop-top/uri/T-0001"),
            VanityAlias(from_="task://shortcutb", to="task://hop-top/uri/T-0002"),
        ],
    )

    with pytest.raises(AmbiguousVanityError) as exc:
        parse("task://shortcut", policy=policy, options=ParseOptions(json_ambiguity=True))

    assert exc.value.to_json() == {
        "input": "task://shortcut",
        "candidates": [
            {"from": "task://shortcuta", "to": "task://hop-top/uri/T-0001", "distance": 1},
            {"from": "task://shortcutb", "to": "task://hop-top/uri/T-0002", "distance": 1},
        ],
    }
    assert json.loads(str(exc.value)) == exc.value.to_json()


def test_parse_contract_action_cases_resolve_to_command_plan() -> None:
    fixture = load_uri_fixture()
    base_policy = policy_from_fixture(fixture)

    for case in fixture["actionCases"]:
        routes = {name: ActionRoute.from_mapping(route) for name, route in case["actionRoutes"].items()}
        policy = Policy(
            default_namespace_segments=base_policy.default_namespace_segments,
            scheme_namespace_segments=base_policy.scheme_namespace_segments,
            action_routes=routes,
        )

        got = parse(case["input"], policy=policy)
        assert_uri_matches(got, case["expected"], case["canonical"])

        plan = resolve_action(got, policy)
        assert plan.action == got.action
        assert plan.command == case["command"]
        assert plan.args == case["args"]


def test_conflicting_action_query_params_fail() -> None:
    policy = Policy(default_namespace_segments=2)

    with pytest.raises(ValueError, match="conflicting action"):
        parse("tlc://org/repo/T-0001?action=task.claim&cmd=task&verb=start", policy=policy)


def test_registry_parse_complete_and_types_parity() -> None:
    policy = Policy(default_namespace_segments=1, scheme_namespace_segments={"task": 2, "repo": 1})
    registry = new_registry_with_policy(policy)

    with pytest.raises(ValueError, match="unknown type"):
        registry.parse("task://hop-top/uri/T-0001")

    with pytest.raises(ValueError, match="registration name"):
        registry.register(TypeRegistration(name=""))

    registry.register(TypeRegistration(name="task", completer=lambda prefix: [x for x in ["T-0001", "T-0002", "T-0099"] if x.startswith(prefix)]))
    registry.register(TypeRegistration(name="repo"))

    got = registry.parse("task://hop-top/uri/T-0001")
    assert got.namespace == "hop-top/uri"
    assert got.id == "T-0001"
    assert registry.complete("task", "T-000") == ["T-0001", "T-0002"]
    assert registry.complete("repo", "") is None
    assert registry.types() == ["repo", "task"]


def test_complete_with_scheme_preserves_scheme_and_surfaces_vanity_candidates() -> None:
    policy = Policy(
        vanity_aliases=[
            VanityAlias(from_="task://shortcuta", to="task://hop-top/uri/T-0001"),
            VanityAlias(from_="task://shortcutb", to="task://hop-top/uri/T-0002"),
        ]
    )
    registry = new_registry_with_policy(policy)
    registry.register(TypeRegistration(name="task", completer=lambda _prefix: ["T-0001"]))

    assert complete_with_scheme(registry, "task", "task://T-").suggestions == ["task://T-0001"]

    out = complete_with_scheme(registry, "task", "task://shortcut")
    assert out.suggestions == [
        "task://shortcuta\tcanonical: task://hop-top/uri/T-0001",
        "task://shortcutb\tcanonical: task://hop-top/uri/T-0002",
    ]


def test_handler_contract_snippets_and_ids() -> None:
    fixture = load_handler_fixture()

    for case in fixture["cases"]:
        spec = HandlerSpec.from_mapping(case["spec"])
        assert spec.handler_id() == case["expected"]["handlerId"]
        if case["expected"].get("desktopFilename"):
            assert desktop_filename(spec) == case["expected"]["desktopFilename"]

        rendered = snippet(case["platform"], spec)
        for expected in case["expected"]["renderedContains"]:
            assert expected in rendered


def test_handler_contract_invalid_cases() -> None:
    fixture = load_handler_fixture()

    for case in fixture["invalidCases"]:
        with pytest.raises(ValueError):
            HandlerSpec.from_mapping(case["spec"]).validate()


def test_handler_unknown_platform() -> None:
    spec = HandlerSpec(vendor="hop-top", app="scheme", language="go", scheme="task", app_path="/usr/bin/task")

    with pytest.raises(ValueError, match="unknown platform"):
        snippet("amiga", spec)
