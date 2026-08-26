# Security invariants

These rules are release blockers.

## Authority

- A generator cannot approve its patch, choose weaker proof, expand its file scope, promote a recipe, or merge its PR.
- `ProofEngine` is the sole normal proof authority. Adapters must not run a parallel host verifier or invent another final digest.
- `PROVEN` requires every configured gate to agree. Missing infrastructure, incomplete evidence, unexpected paths, stale identity, flakiness, or a weaker achieved level yields `NOT_PROVEN`, review, or an explicit inconclusive state.

## Exact identity

- Certificates and delivery bind the repository base, exact patch bytes, expected and actual paths, policy, proof plan/result, runtime identity, and evidence capsule.
- Delivery replays the sealed patch. It never regenerates.
- A base change cannot be handled by restamping a certificate. A Proof Lease remains valid only when verified ancestry and a complete dependency closure establish that all changes are disjoint.
- Cache keys for high-assurance work must bind immutable runtime identity; mutable tags alone are insufficient.

## Execution

- Local execution is observation, not syscall enforcement or sandboxing.
- Untrusted custom/external generators never run as host subprocesses and never fall back to one.
- Generator containers receive only a private working copy, never the live repository or Docker socket; inherit no caller secrets; use exact argv, non-root execution, read-only rootfs, dropped capabilities, no-new-privileges, network disabled by default, resource limits, bounded output, and wall-clock limits.
- Container claims must describe the real boundary: Docker shares the host kernel and the current implementation bind-mounts a private temporary copy.

## Remote input and storage

- Remote release notes, schemas, packages, advisories, redirects, and AI summaries are untrusted data until bounded fetch, provenance capture, parsing, validation, and activation policy complete.
- Symlinks, path traversal, ambiguous file identity, malformed stored records, and unsupported filesystem entries fail closed.
- Evidence is private by default, written atomically with restrictive permissions where supported, and redacted before persistence. Redaction is defense in depth, not a DLP guarantee.
- Integrity hashes detect modification within a local artifact set; they are not signatures or identity authentication.

## Recovery and production

- Rollback changes a path only when current state equals the recorded post-run state.
- Conflicts preserve current data.
- A production regression may preserve evidence, pause future work, notify a human, and prepare a revert for review. Automatic production rollback is always false unless a future, explicit, safely supported policy adds separate authority.

Every change to these boundaries needs tests for refusal, timeout, malformed evidence, weakened capability reporting, and unavailable infrastructure—not only a happy path.
