# Side effects

!!! note "Legacy evaluator heuristic"
    This page documents the original evaluator's fixed severity map. Runtime transactions instead attach path-policy provenance and blast-radius components.

A side effect is an observed mutation that does not match an explicitly declared evaluator target. AgentDiff classifies each side effect using a small, deterministic severity map.

## Current severity map

| Severity | Mutation types |
| --- | --- |
| **Critical** | File or directory deletion, environment-variable removal, process termination, port closure |
| **Warning** | File creation/modification/permission change, directory creation, environment addition/modification, process spawn, port opening |
| **Info** | Any diff type not covered above |

AgentDiff does not inspect file contents or infer that snapshot changes were caused by the child. PID and port set differences are machine-wide observations without ownership attribution. A warning therefore means “unexpected observed difference,” not “confirmed vulnerability.”

## Expected mutations are omitted

When a path matches `target_paths`, its diff contributes to the cleanliness numerator and is not emitted as a side effect. All unmatched diffs remain visible.

```python
for effect in result.side_effects:
    print(effect.severity.value, effect.category, effect.description)
```

A `SideEffect` carries:

- `severity`
- machine-readable `category`
- human-readable `description`
- the original `diff_entry`
- related trajectory step indexes, when path arguments allow attribution
- small metadata such as the diff type

## Reduce noise at capture time

Ignore generated artifacts in `DiffEngine` rather than reclassifying them later:

```python
engine = DiffEngine(
    watch_paths=["/workspace"],
    ignore_patterns=[
        "**/.git/**",
        "**/.venv/**",
        "**/__pycache__/**",
        "**/build/**",
    ],
)
```

Supplying `ignore_patterns` replaces the engine defaults, so include every pattern your run needs.

You can also disable system collectors:

```python
engine = DiffEngine(
    watch_paths=["/workspace"],
    capture_env_vars=False,
    capture_processes=False,
    capture_ports=False,
)
```

See [Cleanliness score](cleanliness.md) for the aggregate metric and [Trajectory tracking](trajectory.md) for attribution.
