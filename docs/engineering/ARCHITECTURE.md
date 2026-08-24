# Architecture

## System shape

```text
remote signal (untrusted)
  → validated API manifest / ChangeSpec
  → exposure and deterministic priority
  → built-in recipe or isolated worker (untrusted patch)
  → policy and impact
  → authoritative ProofEngine
  → exact certificate and sealed patch
  → reviewable PR
  → explicit post-merge outcome evidence
```

The trust boundary is intentionally asymmetric: detection and generation are replaceable inputs; deterministic policy and `ProofEngine` own authorization. A graph may connect evidence, a model may suggest a change, and a test runner may report output, but none can promote its own claim.

## Authoritative components

| Concern | Primary implementation | Authority |
|---|---|---|
| Transaction capture | `transaction/`, `state/`, `evidence/` | Records observed state; does not prove isolation |
| Policy | `policy/` | Deterministic write/process/network-observation decision |
| Impact | `impact/`, `scoring/`, `trust/` | Explains affected paths and future-execution risk |
| API maintenance | `api/` | Scan, simulate, privately generate, verify, certify, deliver |
| Clean-room proof | `proof/engine.py` | Sole normal proof authority |
| Proof strength | `proof/delta.py`, `proof/adversarial.py`, `proof/flake.py`, `proof/lease.py` | Composes with proof; never replaces it |
| Generic maintenance | `maintenance/` | Canonical change, provenance, priority, and scheduling foundations |
| Delivery lifecycle | `api/github_pr.py`, `delivery/` | Replays sealed evidence; no regeneration or merge authority |
| Outcome lifecycle | `outcome/` | Aggregates bounded checks; never performs default production rollback |

## Evidence identity

Stable identities use canonical JSON-compatible payloads and SHA-256 digests. The relevant base, patch, policy, proof plan, runtime image/environment, and evidence references must remain explicit. Stronger or newer evidence creates a new identity; it does not mutate an older certificate into a stronger claim.

`MaintenanceGraph` links lifecycle nodes and evidence references. It is a provenance index, not a second proof engine or source of authorization.

## Execution boundaries

- `agentdiff run` uses a normal host subprocess. Policy around its filesystem effects is principally post-condition observation.
- The built-in deterministic API transform may execute in-process because its exact implementation is trusted with AgentDiff itself.
- Command/external generators are inert exact-argv specifications and require the hardened Docker generator runtime. Docker unavailability is a refusal, not a local downgrade.
- `ProofEngine` independently materializes the captured base plus sealed patch in its clean-room runtime.
- Docker is a container boundary sharing the host kernel, not a VM claim.

## Extension rules

Add new source adapters behind bounded fetch and validation interfaces. Add generator integrations as untrusted exact-argv workers. Add proof dimensions as deterministic evidence that composes beside `ProofResult`. Keep filesystem storage behind small interfaces so local operation never requires a service database.
