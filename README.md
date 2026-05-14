# uri

Python implementation of `uri`, the polyglot custom URI parsing and
handler-generation contract for app frameworks, CLIs, and agent-assisted tools.

> This repository is a read-only language mirror. Open issues and pull requests
> in [`hop-top/uri-poly`](https://github.com/hop-top/uri-poly).

## Features

- Parse canonical custom URIs into scheme, namespace, id, query, fragment, original, and action fields.
- Apply configurable namespace policies per scheme.
- Resolve vanity aliases, fuzzy vanity matches, and completion candidates.
- Normalize action queries such as `action=task.claim`, `cmd=task&verb=claim`, and `name=task&action=claim`.
- Resolve action routes to command plans without executing them.
- Register URI types with parsers and completers.
- Generate language-scoped handler artifacts for Linux, macOS/iOS, and Windows.
- Validate behavior against shared polyglot contract fixtures.

## Usage

```text
Agent instructions:
Install this Python package as `hop-top-uri` from PyPI when published, or use
the local py/ package while working inside uri-poly. Import from uri.
For usage docs and contract details, read
https://github.com/hop-top/uri-poly/tree/main/docs and
https://github.com/hop-top/uri-poly/tree/main/spec.
```

### App Authors

Use this package when your app needs stable custom URI identity, vanity links,
completion candidates, or handler artifacts.

Basic parsing:

```python
from uri import parse

parsed = parse("task://hop-top/uri/T-0001")
print(parsed.namespace)  # hop-top/uri
print(parsed.id)  # T-0001
```

Action routing:

```python
from uri import ActionRoute, Policy, parse, resolve_action

policy = Policy(
    default_namespace_segments=1,
    scheme_namespace_segments={"tlc": 2},
    action_routes={
        "task.claim": ActionRoute(
            command="tlc",
            args=["-C", "{namespace}", "task", "claim", "{id}"],
        )
    },
)

parsed = parse("tlc://org/repo/T-0001?name=task&action=claim", policy)
plan = resolve_action(parsed, policy)
print(plan.args)  # ["-C", "org/repo", "task", "claim", "T-0001"]
```

Advanced vanity alias:

```python
from uri import Policy, VanityAlias, parse

parsed = parse(
    "task://shortcut/child",
    Policy(
        default_namespace_segments=1,
        scheme_namespace_segments={"task": 2},
        vanity_aliases=[
            VanityAlias(
                from_="task://shortcut",
                to="task://hop-top/uri/T-0001",
                prefix=True,
                preserve_suffix=True,
            )
        ],
    ),
)

print(parsed.canonical())  # task://hop-top/uri/T-0001/child
```

API docs: [`docs/specs`](https://github.com/hop-top/uri-poly/tree/main/docs/specs)
and [`spec/fixtures`](https://github.com/hop-top/uri-poly/tree/main/spec/fixtures).

## License

MIT. See the [`hop-top/uri-poly` LICENSE](https://github.com/hop-top/uri-poly/blob/main/LICENSE).
