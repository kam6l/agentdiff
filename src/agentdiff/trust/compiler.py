"""Canonical trust configuration compiler.

``agentdiff bootstrap`` runs the compiler once and writes a single source of
truth under the repository:

- ``agentdiff.yaml``                 canonical policy (filesystem/process/
                                     network/limits/rollback/proof)
- ``.agentdiff/trust.lock``          content-addressed trust identity
- ``.agentdiff/repo-graph.json``     deterministic impact graph
- ``.agentdiff/proof-plan.json``     proof plan (targeted + full) and triggers
- ``.agentdiff/adapters/*.md``       compiled agent instructions per agent

Every artifact is derived from deterministic inspection; no model output is
consulted. Re-running bootstrap is idempotent and refreshes the lock.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentdiff.policy import load_policy, policy_to_dict

from .graph import RepoImpactGraph
from .inspect import RepositoryInspection, RepositoryInspector, inspection_to_policy

_LOCK_SCHEMA_VERSION = 1

_HIGH_RISK_TRIGGERS = (
    ".github/",
    "Dockerfile",
    "Makefile",
    "CMakeLists.txt",
    "nx.json",
    "lerna.json",
    "go.work",
    "pnpm-workspace.yaml",
    "package.json",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "tox.ini",
    "pytest.ini",
    "uv.lock",
    "poetry.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "go.mod",
    "go.sum",
    "Cargo.toml",
    "Cargo.lock",
    "Gemfile",
    "Gemfile.lock",
    "composer.json",
    "composer.lock",
    "pom.xml",
    "build.gradle",
    "AGENTS.md",
    "CLAUDE.md",
    ".codex/",
    ".claude/",
    ".gemini/",
    ".copilot/",
    ".github/CODEOWNERS",
)


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class TrustCompileReport:
    """Result of one bootstrap compile."""

    root: str
    policy_path: str
    lock_path: str
    graph_path: str
    proof_plan_path: str
    adapters_dir: str
    policy_sha256: str
    lock_sha256: str
    inspection_sha256: str
    graph_sha256: str
    proof_plan_sha256: str
    primary_language: str
    package_manager: str | None
    test_tools: tuple[str, ...]
    written: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TrustCompiler:
    """Compile repository inspection into the canonical trust configuration."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        policy_overrides: dict[str, Any] | None = None,
        write_agents: bool = False,
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)
        self.policy_overrides = dict(policy_overrides or {})
        self.write_agents = write_agents

    def compile(self, *, force: bool = False, dry_run: bool = False) -> TrustCompileReport:
        policy_path = self.root / "agentdiff.yaml"
        if policy_path.exists() and not force:
            raise FileExistsError(
                f"trust configuration already exists: {policy_path} (use --force to recompile)"
            )

        inspection = RepositoryInspector(self.root).inspect()
        graph = RepoImpactGraph.from_inspection(self.root)
        policy_dict = inspection_to_policy(inspection)
        if self.policy_overrides:
            policy_dict = _deep_merge(policy_dict, self.policy_overrides)

        policy = load_policy(policy_dict)
        policy_dict = policy_to_dict(policy)

        proof_plan = self._build_proof_plan(inspection, policy_dict)
        graph_dict = graph.serialize()
        inspection_dict = inspection.to_dict()

        inspection_sha = _canonical_digest(inspection_dict)
        graph_sha = _canonical_digest(graph_dict)
        proof_plan_sha = _canonical_digest(proof_plan)
        policy_sha = _canonical_digest(policy_dict)

        lock: dict[str, Any] = {
            "schema_version": _LOCK_SCHEMA_VERSION,
            "generated_at": _utc_now_iso(),
            "inspection_sha256": inspection_sha,
            "graph_sha256": graph_sha,
            "proof_plan_sha256": proof_plan_sha,
            "policy_sha256": policy_sha,
            "repository": {
                "git_head": inspection.git_head,
                "git_dirty_files": inspection.git_dirty_files,
                "lockfile_digests": dict(sorted(inspection.lockfile_digests.items())),
            },
        }
        lock_sha = _canonical_digest(lock)

        written: list[str] = []
        if not dry_run:
            _atomic_write(policy_path, _yaml_dump(policy_dict))
            written.append(str(policy_path))
            agentdiff_dir = self.root / ".agentdiff"
            agentdiff_dir.mkdir(mode=0o700, exist_ok=True)
            lock_path = agentdiff_dir / "trust.lock"
            _atomic_write(lock_path, json.dumps(lock, indent=2, sort_keys=True) + "\n")
            written.append(str(lock_path))
            graph_path = agentdiff_dir / "repo-graph.json"
            _atomic_write(graph_path, json.dumps(graph_dict, indent=2, sort_keys=True) + "\n")
            written.append(str(graph_path))
            proof_plan_path = agentdiff_dir / "proof-plan.json"
            _atomic_write(proof_plan_path, json.dumps(proof_plan, indent=2, sort_keys=True) + "\n")
            written.append(str(proof_plan_path))
            adapters_dir = agentdiff_dir / "adapters"
            adapters_dir.mkdir(mode=0o700, exist_ok=True)
            instructions = self._build_agent_instructions(inspection, policy_dict, proof_plan)
            for filename, content in instructions.items():
                _atomic_write(adapters_dir / filename, content)
                written.append(str(adapters_dir / filename))
            if self.write_agents:
                agents_path = self.root / "AGENTS.md"
                pointer = _AGENTS_POINTER.format(
                    instructions_file=".agentdiff/adapters/agent-instructions.md"
                )
                if agents_path.exists():
                    existing = agents_path.read_text(encoding="utf-8")
                    if "AgentDiff trust configuration" not in existing:
                        agents_path.write_text(
                            existing.rstrip() + "\n\n" + pointer, encoding="utf-8"
                        )
                        written.append(str(agents_path))
                else:
                    agents_path.write_text(pointer, encoding="utf-8")
                    written.append(str(agents_path))
            return TrustCompileReport(
                root=str(self.root),
                policy_path=str(policy_path),
                lock_path=str(agentdiff_dir / "trust.lock"),
                graph_path=str(agentdiff_dir / "repo-graph.json"),
                proof_plan_path=str(agentdiff_dir / "proof-plan.json"),
                adapters_dir=str(adapters_dir),
                policy_sha256=policy_sha,
                lock_sha256=lock_sha,
                inspection_sha256=inspection_sha,
                graph_sha256=graph_sha,
                proof_plan_sha256=proof_plan_sha,
                primary_language=inspection.languages.primary,
                package_manager=inspection.primary_manager,
                test_tools=inspection.toolchain.test_tools,
                written=tuple(written),
            )
        return TrustCompileReport(
            root=str(self.root),
            policy_path=str(policy_path),
            lock_path=str(self.root / ".agentdiff" / "trust.lock"),
            graph_path=str(self.root / ".agentdiff" / "repo-graph.json"),
            proof_plan_path=str(self.root / ".agentdiff" / "proof-plan.json"),
            adapters_dir=str(self.root / ".agentdiff" / "adapters"),
            policy_sha256=policy_sha,
            lock_sha256=lock_sha,
            inspection_sha256=inspection_sha,
            graph_sha256=graph_sha,
            proof_plan_sha256=proof_plan_sha,
            primary_language=inspection.languages.primary,
            package_manager=inspection.primary_manager,
            test_tools=inspection.toolchain.test_tools,
            written=(),
        )

    @staticmethod
    def _build_proof_plan(
        inspection: RepositoryInspection,
        policy_dict: dict[str, Any],
    ) -> dict[str, Any]:
        """Compile the deterministic proof plan (targeted + full)."""
        proof = policy_dict.get("proof") or {}
        return {
            "schema_version": 1,
            "image": proof.get("image"),
            "network": bool(proof.get("network", False)),
            "full": {
                "setup": proof.get("setup", []),
                "build": proof.get("build", []),
                "tests": proof.get("tests", []),
            },
            "targeted": {
                "static": TrustCompiler._static_phases(inspection, proof),
                "tests": proof.get("tests", []),
            },
            "high_risk_triggers": sorted(_HIGH_RISK_TRIGGERS),
            "test_patterns": list(inspection.toolchain.test_patterns),
            "primary_manager": inspection.primary_manager,
        }

    @staticmethod
    def _static_phases(inspection: RepositoryInspection, proof: dict[str, Any]) -> list[list[str]]:
        if inspection.primary_manager == "go" and "go" in inspection.languages.languages:
            return [["go", "vet", "./..."]]
        if inspection.primary_manager == "cargo":
            return [["cargo", "check", "--locked"]]
        if "python" in inspection.languages.languages:
            return [["python", "-m", "compileall", "-q", "src"]]
        if "typescript" in inspection.languages.languages or (
            "javascript" in inspection.languages.languages
        ):
            return (
                [["npx", "tsc", "--noEmit"]]
                if "typescript" in inspection.languages.languages
                else []
            )
        return list(proof.get("build", []))

    def _build_agent_instructions(
        self,
        inspection: RepositoryInspection,
        policy_dict: dict[str, Any],
        proof_plan: dict[str, Any],
    ) -> dict[str, str]:
        filesystem = policy_dict.get("filesystem", {})
        allow = filesystem.get("allow_write", [])
        review = filesystem.get("review", [])
        deny = filesystem.get("deny", [])
        proof = policy_dict.get("proof", {})

        def rule_lines(patterns: list[str]) -> str:
            return "\n".join(f"- `{pattern}`" for pattern in patterns) or "- (none)"

        body = f"""# AgentDiff trust configuration (compiled)

> Generated deterministically by `agentdiff bootstrap`. Do not hand-edit;
> re-run bootstrap to refresh. This is the single source of truth for agent
> file boundaries and verification in this repository.

## Language / toolchain

- Primary language: `{inspection.languages.primary}`
- Package manager: `{inspection.primary_manager or "none detected"}`
- Test tooling: {", ".join(inspection.toolchain.test_tools) or "none detected"}
- Monorepo layout: `{inspection.monorepo.kind}`

## File boundaries

### Allowed to write
{rule_lines(allow)}

### Requires review before promotion (config, CI, dependencies)
{rule_lines(review)}

### Never write (deny)
{rule_lines(deny)}

Default for unmatched paths: `{filesystem.get("default", "review")}`.

## Verification recipe (clean room)

```bash
# setup
{_fmt_commands(proof.get("setup", []))}
# build
{_fmt_commands(proof.get("build", []))}
# tests
{_fmt_commands(proof.get("tests", []))}
```

Changes to dependency files, CI workflows, Dockerfiles, build configuration,
agent instructions, or security paths widen proof to the full suite and require
human/owner review before promotion.

## Process

- Keep changes inside the allowed write paths.
- Do not add dependencies, change CI, or modify build configuration without
  explicit authorization.
- Never touch `.env*`, `.git/**`, `.ssh/**`, keys, or credentials.
"""
        agent_files: dict[str, str] = {}
        for name, header in (
            ("agent-instructions.md", "Agent instructions"),
            ("CLAUDE.md", "Claude instructions"),
            ("codex.md", "Codex instructions"),
            ("gemini.md", "Gemini instructions"),
            ("copilot.md", "Copilot instructions"),
        ):
            agent_files[name] = f"# {header}\n\n{body}"
        return agent_files


_AGENTS_POINTER = """## AgentDiff trust configuration

AgentDiff has compiled a canonical trust configuration for this repository.
Read `{instructions_file}` before making changes; it defines allowed write
paths, protected paths, and the deterministic verification recipe.
"""


def _fmt_commands(commands: list[list[str]]) -> str:
    if not commands:
        return "(none)"
    return "\n".join("    " + " ".join(command) for command in commands)


def _yaml_dump(policy_dict: dict[str, Any]) -> str:
    """Serialize policy to YAML with stable ordering (yaml is a runtime dep)."""
    import yaml

    return yaml.safe_dump(policy_dict, sort_keys=False, default_flow_style=False)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_trust_lock(root: str | os.PathLike[str]) -> dict[str, Any] | None:
    """Read the canonical trust lock if present."""
    lock_path = Path(root).expanduser().resolve(strict=False) / ".agentdiff" / "trust.lock"
    if not lock_path.is_file():
        return None
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
