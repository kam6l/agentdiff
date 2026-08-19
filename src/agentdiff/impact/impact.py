"""Deterministic impact-aware proof planning.

The impact engine turns a set of changed files into the minimum strong proof:

- ``static``   fast deterministic checks (compile/vet/type-check)
- ``targeted`` static + the tests that cover affected modules
- ``full``     the complete repository proof

High-risk changes (dependencies, CI, Dockerfiles, build configuration, agent
instructions, security paths) always widen proof to ``full``. All decisions
are deterministic path/import analysis; no model is involved.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Iterable

from agentdiff.pathing import normalize_relative_path
from agentdiff.trust.compiler import load_trust_lock
from agentdiff.trust.inspect import _is_security_path

from .cache import ProofCacheKey

if TYPE_CHECKING:
    from agentdiff.trust.graph import RepoImpactGraph

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

_DEPENDENCY_FILE_NAMES = frozenset(
    {
        "cargo.lock",
        "cargo.toml",
        "composer.json",
        "composer.lock",
        "gemfile",
        "gemfile.lock",
        "go.mod",
        "go.sum",
        "package-lock.json",
        "package.json",
        "pnpm-lock.yaml",
        "poetry.lock",
        "pyproject.toml",
        "requirements.txt",
        "uv.lock",
        "yarn.lock",
    }
)


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_proof_cache_key(
    *,
    root: str | Path,
    base_digest: str,
    patch_digest: str,
    image_digest: str,
    plan_digest: str,
    target: str = "full",
) -> ProofCacheKey:
    """Build the content-addressed proof cache key from sealed capsule evidence.

    ``base_digest`` is the sealed source snapshot digest, ``patch_digest`` the
    sealed mutation manifest digest, ``image_digest`` the runtime image name
    plus repository digest when known, and ``plan_digest`` the exact argv proof
    plan. Lockfile digests come from the canonical trust lock when present.
    """
    root_path = Path(root).expanduser().resolve(strict=True)
    lock_digest = "no-trust-lock"
    trust_lock = load_trust_lock(root_path)
    if trust_lock is not None:
        repository = trust_lock.get("repository") or {}
        lock_digests = repository.get("lockfile_digests") or {}
        lock_digest = (
            _canonical_digest({"locks": dict(sorted(lock_digests.items()))})
            if lock_digests
            else "no-lockfiles"
        )
    return ProofCacheKey(
        base_digest=base_digest,
        patch_digest=patch_digest,
        lock_digest=lock_digest,
        image_digest=image_digest,
        plan_digest=plan_digest,
        target=target,
    )


def classify_risk(path: str) -> str:
    """Return ``full`` when a path is high-risk, else ``targeted``."""
    normalized = normalize_relative_path(path)
    posix = PurePosixPath(normalized)
    name = posix.name.lower()
    if name in _DEPENDENCY_FILE_NAMES:
        return "full"
    if _is_security_path(normalized):
        return "full"
    if any(
        normalized.startswith(trigger) or normalized == trigger for trigger in _HIGH_RISK_TRIGGERS
    ):
        return "full"
    return "targeted"


@dataclass(frozen=True, slots=True)
class ProofImpactPlan:
    """The deterministic proof to run for one set of changed files."""

    level: str  # "static" | "targeted" | "full"
    changed_paths: tuple[str, ...]
    triggers: tuple[str, ...]
    modules: tuple[str, ...]
    tests: tuple[str, ...]
    build_targets: tuple[str, ...]
    static_commands: tuple[tuple[str, ...], ...]
    test_commands: tuple[tuple[str, ...], ...]
    full_setup: tuple[tuple[str, ...], ...]
    full_build: tuple[tuple[str, ...], ...]
    full_tests: tuple[tuple[str, ...], ...]
    plan_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "level": self.level,
            "changed_paths": list(self.changed_paths),
            "triggers": list(self.triggers),
            "modules": list(self.modules),
            "tests": list(self.tests),
            "build_targets": list(self.build_targets),
            "static_commands": [list(cmd) for cmd in self.static_commands],
            "test_commands": [list(cmd) for cmd in self.test_commands],
            "full_setup": [list(cmd) for cmd in self.full_setup],
            "full_build": [list(cmd) for cmd in self.full_build],
            "full_tests": [list(cmd) for cmd in self.full_tests],
            "plan_digest": self.plan_digest,
        }


class ImpactEngine:
    """Compute the minimum strong proof for a patch using the impact graph."""

    def __init__(
        self,
        root: str | Path,
        *,
        graph: RepoImpactGraph | None = None,
        proof_plan: dict[str, Any] | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        self.graph = graph
        self.proof_plan = proof_plan

    def plan(self, changed_paths: Iterable[str]) -> ProofImpactPlan:
        normalized = tuple(sorted(normalize_relative_path(path) for path in changed_paths))
        triggers: list[str] = []
        any_full = False
        for path in normalized:
            risk = classify_risk(path)
            if risk == "full":
                any_full = True
                triggers.append(path)

        impact = self.graph.affected(normalized) if self.graph is not None else None
        modules = impact.modules if impact is not None else ()
        tests = self._test_paths(impact.tests) if impact is not None else ()
        build_targets = impact.build_targets if impact is not None else ()

        full_setup, full_build, full_tests, static_commands = self._phases()
        level = "full" if any_full or not normalized else "targeted"
        test_commands: tuple[tuple[str, ...], ...]
        if level == "full":
            test_commands = full_tests
        else:
            targeted = self._targeted_test_commands(tests)
            test_commands = targeted if targeted else full_tests
            if not test_commands:
                level = "static"

        unsigned = {
            "schema_version": 1,
            "level": level,
            "changed_paths": normalized,
            "triggers": tuple(triggers),
            "modules": modules,
            "tests": tests,
            "static_commands": static_commands,
            "test_commands": test_commands,
        }
        return ProofImpactPlan(
            level=level,
            changed_paths=normalized,
            triggers=tuple(triggers),
            modules=modules,
            tests=tests,
            build_targets=build_targets,
            static_commands=static_commands,
            test_commands=test_commands,
            full_setup=full_setup,
            full_build=full_build,
            full_tests=full_tests,
            plan_digest=_canonical_digest(unsigned),
        )

    def _test_paths(self, test_module_ids: Iterable[str]) -> tuple[str, ...]:
        """Map test module ids back to concrete file paths for test runners."""
        paths: set[str] = set()
        for module_id in test_module_ids:
            if self.graph is None:
                continue
            files = self.graph.module_to_files.get(module_id, ())
            preferred = [path for path in files if not path.endswith("__init__.py")] or list(files)
            paths.update(preferred)
        if not paths:
            return tuple(sorted(test_module_ids))
        return tuple(sorted(paths))

    def _phases(self) -> tuple[tuple[tuple[str, ...], ...], ...]:
        if self.proof_plan is not None:
            full = self.proof_plan.get("full") or {}
            targeted = self.proof_plan.get("targeted") or {}
            setup = tuple(tuple(cmd) for cmd in full.get("setup", []))
            build = tuple(tuple(cmd) for cmd in full.get("build", []))
            tests = tuple(tuple(cmd) for cmd in full.get("tests", []))
            static = tuple(tuple(cmd) for cmd in targeted.get("static", []))
            return setup, build, tests, static
        return (), (), (), ()

    def _targeted_test_commands(self, tests: Iterable[str]) -> tuple[tuple[str, ...], ...]:
        test_paths = tuple(sorted(tests))
        if not test_paths:
            return ()
        plan = self.proof_plan or {}
        primary = str(plan.get("primary_manager") or "")
        if primary in {"uv", "poetry", "pip"}:
            return (("python", "-m", "pytest", "-q", *test_paths),)
        if primary in {"npm", "pnpm", "yarn"}:
            suffix = " ".join(test_paths)
            return ((primary, "test", "--", suffix),)
        if primary == "go":
            directories = sorted({PurePosixPath(path).parent.as_posix() for path in test_paths})
            return (("go", "test", *directories),)
        if primary == "cargo":
            return (("cargo", "test", "--locked"),)
        return ()
