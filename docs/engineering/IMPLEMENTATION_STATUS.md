# Implementation status

This table distinguishes integrated product behavior from isolated foundations and roadmap work. It is a claim-control document, not a schedule.

| Capability | Status | Current boundary |
|---|---|---|
| Python provider scan/check/simulate | Available | OpenAI is the complete narrow path; Stripe generation is not launch-grade |
| Deterministic Chat Completions → Responses transform | Available | Text-only supported shapes; complex/dynamic shapes require review |
| Private generation, policy, impact, ProofEngine | Available | Clean-room proof requires Docker by default |
| Integrity certificates and exact PR delivery | Available | SHA-256 integrity, not identity signatures; no auto-merge |
| Explicit multi-repository campaigns | Available | Local configured repositories; no organization discovery or bulk merge |
| Provider discovery and data-only plugins | Available | Candidates stay untrusted until validation/activation |
| Generic ChangeSpec, Maintenance Graph, priority | Foundation | Deterministic local models/store; not the default migration schema or scheduler loop |
| Hardened custom generator runtime | Foundation | Docker only, exact argv, no host fallback; private copy is bind-mounted and shares host kernel |
| DeltaProof and adversarial proof | Foundation | Tested composable evidence; not yet a required default ProofEngine gate |
| Patch minimizer | Foundation | Bounded ddmin-style engine; not wired into default migration |
| Proof Lease | Foundation | Pure fail-closed evaluator; no certificate restamping or default integration |
| PR reconciliation | Foundation | Pure reuse/update/stale/supersede decision; never regenerates or merges |
| Post-merge outcome verification | Foundation | Pure/pluggable bounded checks; no production adapter or automatic rollback |
| Maintenance scheduler | Foundation | Deterministic resource/window decisions; no background service |
| Flake Firewall | Foundation | Deterministic classification; flaky evidence cannot count as proof |
| Continuous Change Radar | Roadmap | Bounded source adapters and activation workflow remain to be integrated |
| Organization Exposure Graph | Roadmap | Existing local scanner/impact evidence is the starting seam |
| Verified Recipe promotion | Roadmap | Candidate → fixtures → proof → trusted approval lifecycle is not implemented |
| Operational pause/resume and post-merge adapters | Roadmap | Requires explicit external capabilities and permission boundaries |
| Authenticated attestations | Roadmap | Use Sigstore/in-toto/OIDC rather than custom cryptography |

## Should not be implemented

- Generator/model self-approval or proof selection.
- Silent Docker-to-host fallback for untrusted execution.
- Regeneration during delivery or certificate restamping after base movement.
- Default auto-merge or default production rollback.
- Claims of a hosted dashboard, customer telemetry, partnerships, adoption, or benchmark gains without real evidence.
- A second verifier that can disagree with or bypass `ProofEngine`.
