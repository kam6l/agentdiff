# Security policy

## Supported versions

AgentDiff is pre-release software. Security fixes are applied to the latest commit on `main`; no stable release line is supported yet.

## Reporting a vulnerability

Please do not publish credentials, private trajectories, environment snapshots, or exploit details in a public issue.

Open a minimal issue at <https://github.com/kam6l/agentdiff/issues> requesting a private disclosure channel. Include only a high-level impact summary and affected component. A maintainer will respond with a private contact path.

## Sensitive data

AgentDiff snapshots can contain filesystem metadata, process IDs, port information, and environment-variable values. Secret-like environment names are excluded by default, but no denylist can identify every sensitive variable. Review artifacts before sharing them and disable collectors that are unnecessary for the evaluation.
