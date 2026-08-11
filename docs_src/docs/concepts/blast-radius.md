# Blast-radius scoring

Blast radius is an explainable estimate of observed side-effect risk. It is **not** a probability, vulnerability severity, or proof of malicious behavior.

The scorer is deterministic. It adds named evidence components, records each component's count and weight, then caps the final score at 100.

## Default weights

| Evidence | Points |
| --- | ---: |
| Review-created file | 8 |
| Review-modified file | 4 |
| Review-deleted file | 12 |
| Denied creation/modification | 30 |
| Denied deletion | 40 |
| Sensitive path | 35 |
| Dependency manifest/lockfile change | 8 |
| Mode change | 8 |
| Uncleaned owned process | 10 |
| Newly observed listening endpoint | 5 |
| Budget violation | 12 |
| Each unexpected mutation after the first five | 2 |

A mutation can produce multiple components. For example, modifying a denied `.env` path adds both denied-mutation and sensitive-path evidence.

## Levels

| Score | Level |
| ---: | --- |
| 0–20 | low |
| 21–40 | moderate |
| 41–70 | high |
| 71–100 | critical |

The uncapped raw score remains in the result so repeated high-risk evidence is not hidden by the 100-point presentation cap.

## Example

```text
.env modified             denied mutation      30
.env sensitive path       sensitive path        35
--------------------------------------------------
raw / capped score                              65
level                                         high
```

Every serialized result includes:

- final score and raw score;
- level;
- component name, count, per-item weight, points, and detail; and
- evidence counts such as unexpected files, sensitive paths, deletions, dependency files, processes, ports, and budget violations.

## Configure weights

```yaml
version: 1
scoring:
  weights:
    denied_mutation: 45
    denied_deletion: 55
    sensitive_path: 40
    opened_port: 3
```

Only declared weight names are accepted. Values must be nonnegative integers. Setting a weight to zero removes its point contribution but does not remove the underlying evidence from the result.

## Interpretation limits

- A high score means the configured deterministic model accumulated high-impact evidence; it does not prove intent.
- An allowed change can still count for mode or dependency impact.
- Listening endpoints are machine-wide observations and may be unrelated to the child.
- Process residue depends on what local polling observed and could clean safely.
- Ignored, unreadable, unsupported, or oversized entries can reduce visibility; observation warnings should be reviewed alongside the score.

Use the component list, policy provenance, and raw mutations for decisions. Do not treat the number alone as an authorization oracle.
