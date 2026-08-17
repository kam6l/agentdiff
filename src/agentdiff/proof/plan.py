"""Deterministic proof-plan discovery and trusted verification provenance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from pathlib import Path

    from agentdiff.evidence import PatchBundle, PatchEntry
    from agentdiff.policy import Policy


_PYTHON_CONFIG_NAMES = frozenset(
    {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "tox.ini",
        "pytest.ini",
        "conftest.py",
        "requirements.txt",
        "requirements-dev.txt",
        "Pipfile",
        "Pipfile.lock",
        "poetry.lock",
        "uv.lock",
    }
)

_NODE_CONFIG_NAMES = frozenset(
    {
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "tsconfig.json",
        ".npmrc",
    }
)

_CI_BUILD_CONFIG_NAMES = frozenset(
    {
        "Makefile",
        "Dockerfile",
        "CMakeLists.txt",
    }
)


@dataclass(frozen=True, slots=True)
class TrustedVerificationPlan:
    """A deterministic verification plan with provenance and tamper-detection."""

    image: str
    network: bool
    setup: tuple[tuple[str, ...], ...]
    build: tuple[tuple[str, ...], ...]
    tests: tuple[tuple[str, ...], ...]
    source: str
    trusted: bool
    plan_digest: str
    tampered_files: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "image": self.image,
            "network": self.network,
            "setup": [list(cmd) for cmd in self.setup],
            "build": [list(cmd) for cmd in self.build],
            "tests": [list(cmd) for cmd in self.tests],
            "source": self.source,
            "trusted": self.trusted,
            "plan_digest": self.plan_digest,
            "tampered_files": list(self.tampered_files),
            "reason": self.reason,
        }


def _compute_plan_digest(
    setup: Iterable[Iterable[str]], build: Iterable[Iterable[str]], tests: Iterable[Iterable[str]]
) -> str:
    payload = {
        "setup": [list(cmd) for cmd in setup],
        "build": [list(cmd) for cmd in build],
        "tests": [list(cmd) for cmd in tests],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def select_trusted_verification_plan(
    base_root: Path,
    policy: Policy,
    patch_bundle: PatchBundle | None = None,
    patch_entries: Iterable[PatchEntry] | None = None,
) -> TrustedVerificationPlan:
    """Select verification recipe adhering to strict trust hierarchy.

    Trust hierarchy:
    1. Explicit policy verification commands (always trusted).
    2. Auto-discovery from pre-run base source if patch did NOT tamper with config files.
    3. If patch modified auto-discovered test/build configs without explicit policy, mark UNTRUSTED.
    4. If no tests configured or discoverable, mark UNTRUSTED.
    """
    configured = bool(policy.proof.setup or policy.proof.build or policy.proof.tests)
    if configured:
        digest = _compute_plan_digest(policy.proof.setup, policy.proof.build, policy.proof.tests)
        has_tests = bool(policy.proof.tests)
        return TrustedVerificationPlan(
            image=policy.proof.image or "python:3.12-slim",
            network=policy.proof.network,
            setup=policy.proof.setup,
            build=policy.proof.build,
            tests=policy.proof.tests,
            source="policy",
            trusted=has_tests,
            plan_digest=digest,
            tampered_files=(),
            reason="explicit trusted policy configuration"
            if has_tests
            else "policy specifies no test commands",
        )

    # Auto-discovery inspects the base_root (pre-run state)
    modified_paths: set[str] = set()
    if patch_bundle is not None:
        modified_paths.update(entry.path for entry in patch_bundle.manifest.entries)
    if patch_entries is not None:
        modified_paths.update(entry.path for entry in patch_entries)

    if (base_root / "uv.lock").is_file():
        relevant_tampered = tuple(
            sorted(
                p for p in modified_paths if p in _PYTHON_CONFIG_NAMES or p.startswith(".github/")
            )
        )
        trusted = len(relevant_tampered) == 0
        setup_cmds: tuple[tuple[str, ...], ...] = (("uv", "sync", "--frozen", "--no-cache"),)
        build_cmds: tuple[tuple[str, ...], ...] = (("uv", "build"),)
        test_cmds: tuple[tuple[str, ...], ...] = (("uv", "run", "pytest", "-q"),)
        tampered_msg = ", ".join(relevant_tampered)
        digest = _compute_plan_digest(setup_cmds, build_cmds, test_cmds)
        reason = (
            "discovered from base uv.lock"
            if trusted
            else f"patch modified test/build infrastructure without policy override: {tampered_msg}"
        )
        return TrustedVerificationPlan(
            image=policy.proof.image or "ghcr.io/astral-sh/uv:python3.12-bookworm-slim",
            network=policy.proof.network,
            setup=setup_cmds,
            build=build_cmds,
            tests=test_cmds,
            source="auto:uv",
            trusted=trusted,
            plan_digest=digest,
            tampered_files=relevant_tampered,
            reason=reason,
        )

    if (base_root / "pyproject.toml").is_file():
        relevant_tampered = tuple(
            sorted(
                p for p in modified_paths if p in _PYTHON_CONFIG_NAMES or p.startswith(".github/")
            )
        )
        trusted = len(relevant_tampered) == 0
        python = ".agentdiff-proof/venv/bin/python"
        py_setup: tuple[tuple[str, ...], ...] = (
            ("python", "-m", "venv", ".agentdiff-proof/venv"),
            (python, "-m", "pip", "install", "--no-cache-dir", "-e", "."),
        )
        py_build: tuple[tuple[str, ...], ...] = ((python, "-m", "compileall", "-q", "src"),)
        py_tests: tuple[tuple[str, ...], ...] = ((python, "-m", "pytest", "-q"),)
        digest = _compute_plan_digest(py_setup, py_build, py_tests)
        tampered_msg = ", ".join(relevant_tampered)
        reason = (
            "discovered from base pyproject.toml"
            if trusted
            else f"patch modified test/build infrastructure without policy override: {tampered_msg}"
        )
        return TrustedVerificationPlan(
            image=policy.proof.image or "python:3.12-slim",
            network=policy.proof.network,
            setup=py_setup,
            build=py_build,
            tests=py_tests,
            source="auto:python",
            trusted=trusted,
            plan_digest=digest,
            tampered_files=relevant_tampered,
            reason=reason,
        )

    if (base_root / "package-lock.json").is_file() or (base_root / "package.json").is_file():
        relevant_tampered = tuple(
            sorted(p for p in modified_paths if p in _NODE_CONFIG_NAMES or p.startswith(".github/"))
        )
        trusted = len(relevant_tampered) == 0
        npm_setup: tuple[tuple[str, ...], ...] = (
            (("npm", "ci"),)
            if (base_root / "package-lock.json").is_file()
            else (("npm", "install"),)
        )
        npm_build: tuple[tuple[str, ...], ...] = (("npm", "run", "build", "--if-present"),)
        npm_tests: tuple[tuple[str, ...], ...] = (("npm", "test"),)
        digest = _compute_plan_digest(npm_setup, npm_build, npm_tests)
        tampered_msg = ", ".join(relevant_tampered)
        reason = (
            "discovered from base package manifest"
            if trusted
            else f"patch modified test/build infrastructure without policy override: {tampered_msg}"
        )

        return TrustedVerificationPlan(
            image=policy.proof.image or "node:22-slim",
            network=policy.proof.network,
            setup=npm_setup,
            build=npm_build,
            tests=npm_tests,
            source="auto:npm",
            trusted=trusted,
            plan_digest=digest,
            tampered_files=relevant_tampered,
            reason=reason,
        )

    return TrustedVerificationPlan(
        image=policy.proof.image or "python:3.12-slim",
        network=policy.proof.network,
        setup=(),
        build=(),
        tests=(),
        source="unconfigured",
        trusted=False,
        plan_digest=_compute_plan_digest((), (), ()),
        tampered_files=(),
        reason="no deterministic test command is configured or discoverable",
    )
