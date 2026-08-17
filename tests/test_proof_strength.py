"""Adversarial proof tests: verifier tampering, baseline verifier, strength."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agentdiff.policy import ProofPolicy, load_policy
from agentdiff.proof import (
    ProofEngine,
    ProofPhaseResult,
    ProofStrengthLabel,
    ProofStrengthLevel,
    ProofVerdict,
    VerifierIndependence,
    analyze_verifier_mutations,
    compute_proof_strength,
    is_verifier_related,
)
from agentdiff.proof.plan import select_trusted_verification_plan
from agentdiff.runtime import CleanupReport, RuntimeCapability, RuntimeControlLevel, RuntimeResult
from agentdiff.transaction import AgentRunTransaction, RunStore


def trust_policy() -> object:
    return load_policy(
        {
            "version": 2,
            "filesystem": {"allow_write": ["**"], "default": "allow"},
            "process": {"allow": ["agent"], "default": "deny"},
            "network": {"mode": "off"},
            "proof": {"network": False, "tests": [["tests"]]},
        }
    )


class IsolatedRuntime:
    """Test backend with a private writable copy like DockerRuntime."""

    def __init__(self, mutator) -> None:
        self.mutator = mutator
        self.source: Path | None = None
        self.temporary = None
        self.workspace: Path | None = None

    @property
    def capabilities(self):
        from agentdiff.runtime import RuntimeCapabilities, RuntimeControlLevel

        return RuntimeCapabilities(
            backend="test-isolated",
            filesystem=RuntimeControlLevel.SANDBOXED,
            host_repository=RuntimeControlLevel.SANDBOXED,
            network=RuntimeControlLevel.BLOCKED,
            processes=RuntimeControlLevel.SANDBOXED,
            resources=RuntimeControlLevel.SANDBOXED,
            privileges=RuntimeControlLevel.SANDBOXED,
            private_workspace=True,
            supports_live_safety=True,
            supports_source_snapshot=True,
        )

    def configure_source(self, source: Path) -> None:
        self.source = source

    def configure_safety(self, _watcher) -> None:
        return None

    def configure_safety(self, _controller) -> None:
        return None

    def run(self, argv, **_kwargs) -> RuntimeResult:
        import shutil
        import tempfile

        assert self.source is not None
        self.temporary = Path(tempfile.mkdtemp(prefix="agentdiff-test-isolated-"))
        self.workspace = self.temporary / "workspace"
        shutil.copytree(self.source, self.workspace)
        self.mutator(self.workspace)
        return RuntimeResult(
            argv=tuple(argv),
            cwd="/workspace",
            returncode=0,
            timed_out=False,
            duration_seconds=0.01,
            backend="test-isolated",
            enforcement="isolated_private_workspace",
            capabilities=(),
            observation_root=str(self.workspace),
        )

    def cleanup(self, _processes, **_kwargs) -> CleanupReport:
        return CleanupReport()

    def close(self) -> None:
        if self.temporary is not None:
            import shutil

            shutil.rmtree(self.temporary)
            self.temporary = None


class RecordingProofEnvironment:
    """Fake clean room that asserts baseline overlay state during run."""

    def __init__(
        self,
        *,
        workspace: Path,
        image: str,
        network: bool,
        baseline_passes: bool = True,
        expect_overlay: str | None = None,
        expected_overlay_content: str = "",
    ) -> None:
        self.workspace = workspace
        self.baseline_passes = baseline_passes
        self.expect_overlay = expect_overlay
        self.expected_overlay_content = expected_overlay_content
        self.baseline_seen = False

    def start(self) -> dict[str, object]:
        return {"schema_version": 1, "backend": "test", "clean_environment": True}

    def run_phase(self, phase: str, command, *, timeout_seconds: float) -> ProofPhaseResult:
        assert timeout_seconds > 0
        if phase == "tests":
            return ProofPhaseResult(
                phase=phase,
                command=tuple(command),
                status="PASS",
                returncode=0,
                duration_seconds=0.01,
                tests_passed=2,
                tests_total=2,
            )
        if phase == "baseline_tests":
            self.baseline_seen = True
            if self.expect_overlay is not None:
                assert (
                    self.workspace / self.expect_overlay
                ).read_text(encoding="utf-8") == self.expected_overlay_content, (
                    f"baseline did not restore {self.expect_overlay}"
                )
            status = "PASS" if self.baseline_passes else "FAIL"
            return ProofPhaseResult(
                phase=phase,
                command=tuple(command),
                status=status,
                returncode=0 if self.baseline_passes else 1,
                duration_seconds=0.01,
                tests_passed=2 if self.baseline_passes else 0,
                tests_total=2,
            )
        return ProofPhaseResult(
            phase=phase,
            command=tuple(command),
            status="PASS",
            returncode=0,
            duration_seconds=0.01,
        )

    def close(self) -> None:
        return None


def run_and_prove(
    tmp_path: Path,
    mutator,
    *,
    baseline_passes: bool = True,
    expect_overlay: str | None = None,
    expected_overlay_content: str = "",
) -> tuple[str, object]:
    runtime = IsolatedRuntime(mutator)
    result = AgentRunTransaction(
        root=tmp_path,
        policy=trust_policy(),
        runtime=runtime,
        task="proof test",
    ).run(["agent"])
    assert result.status == "passed"
    return result.run_id, ProofEngine(
        tmp_path,
        result.run_id,
        environment_factory=lambda workspace, image, network: RecordingProofEnvironment(
            workspace=workspace,
            image=image,
            network=network,
            baseline_passes=baseline_passes,
            expect_overlay=expect_overlay,
            expected_overlay_content=expected_overlay_content,
        ),
    ).prove(timeout_seconds=5)


# ---------------------------------------------------------------------------
# Verifier-file classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_login.py",
        "tests/conftest.py",
        "test/unit_test.py",
        "__tests__/app.test.js",
        "conftest.py",
        "pytest.ini",
        "tox.ini",
        "noxfile.py",
        "setup.py",
        "setup.cfg",
        "Makefile",
        "Dockerfile",
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "uv.lock",
        "poetry.lock",
        "pyproject.toml",
        "vitest.config.ts",
        "jest.config.js",
        "playwright.config.ts",
        "requirements-dev.txt",
        ".github/workflows/ci.yml",
        "src/app.test.tsx",
        "src/test_util.py",
    ],
)
def test_verifier_related_detected(path: str) -> None:
    assert is_verifier_related(path)


@pytest.mark.parametrize(
    "path",
    [
        "src/app.py",
        "README.md",
        "data/input.csv",
        "docs/index.md",
        "src/util.rs",
        "assets/logo.png",
    ],
)
def test_verifier_related_negative(path: str) -> None:
    assert not is_verifier_related(path)


def test_verifier_mutation_report_classifies_changes() -> None:
    report = analyze_verifier_mutations(
        [
            ("tests/test_login.py", "modified"),
            ("conftest.py", "modified"),
            ("tests/test_new.py", "created"),
            ("tests/test_deleted.py", "deleted"),
            ("src/app.py", "modified"),
        ]
    )
    assert report.modified_count == 2
    assert report.existing_changed == ("conftest.py", "tests/test_login.py")
    assert report.added == ("tests/test_new.py",)
    assert report.removed == ("tests/test_deleted.py",)
    assert report.any_modification


def test_plan_untrusted_when_test_files_modified(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_x(): pass\n", encoding="utf-8")
    policy = load_policy({"version": 2})
    tampered_entry = {
        "path": "tests/test_app.py",
        "change_type": "modified",
        "decision": "allow",
        "base_sha256": "a",
        "result_sha256": "b",
        "base_mode": 0o644,
        "result_mode": 0o644,
        "size": 5,
        "materialized": True,
        "reason": "",
    }
    from agentdiff.evidence import PatchEntry

    plan = select_trusted_verification_plan(
        tmp_path,
        policy,
        patch_entries=(PatchEntry.from_dict(tampered_entry),),
    )
    assert plan.trusted is False
    assert "tests/test_app.py" in plan.tampered_files


# ---------------------------------------------------------------------------
# Proof-strength model
# ---------------------------------------------------------------------------


def test_proof_strength_matrix() -> None:
    assert compute_proof_strength(
        clean_environment="FAIL",
        trusted_plan=False,
        baseline_verifier="SKIPPED",
        baseline_available=False,
        verifier_files_changed=0,
    ) == (
        ProofStrengthLevel.L0_EXECUTION_ONLY,
        ProofStrengthLabel.WEAK,
        VerifierIndependence.WEAK,
    )
    assert compute_proof_strength(
        clean_environment="PASS",
        trusted_plan=False,
        baseline_verifier="SKIPPED",
        baseline_available=False,
        verifier_files_changed=0,
    ) == (ProofStrengthLevel.L1_CLEAN_ROOM, ProofStrengthLabel.WEAK, VerifierIndependence.WEAK)
    assert compute_proof_strength(
        clean_environment="PASS",
        trusted_plan=True,
        baseline_verifier="SKIPPED",
        baseline_available=False,
        verifier_files_changed=0,
    ) == (
        ProofStrengthLevel.L2_TRUSTED_COMMAND,
        ProofStrengthLabel.REVIEW,
        VerifierIndependence.WEAK,
    )
    assert compute_proof_strength(
        clean_environment="PASS",
        trusted_plan=True,
        baseline_verifier="PASS",
        baseline_available=True,
        verifier_files_changed=0,
    ) == (
        ProofStrengthLevel.L3_BASELINE_VERIFIER,
        ProofStrengthLabel.STRONG,
        VerifierIndependence.STRONG,
    )


# ---------------------------------------------------------------------------
# Baseline verifier end-to-end
# ---------------------------------------------------------------------------


def test_baseline_verifier_runs_against_restored_base_tests(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_value():\n    assert True\n", encoding="utf-8"
    )

    def mutator(workspace: Path) -> None:
        (workspace / "src" / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        (workspace / "tests" / "test_app.py").write_text(
            "def test_value():\n    assert True  # weakened?\n", encoding="utf-8"
        )

    run_id, proof = run_and_prove(
        tmp_path,
        mutator,
        expect_overlay="tests/test_app.py",
        expected_overlay_content="def test_value():\n    assert True\n",
    )
    assert proof.verdict is ProofVerdict.PROVEN
    assert proof.verifier_files_changed >= 1
    assert "tests/test_app.py" in proof.verifier_changes
    assert proof.baseline_available is True
    assert proof.baseline_verifier == "PASS"
    assert proof.patched_tests_total == 2
    assert proof.baseline_tests_total == 2
    assert proof.proof_strength == ProofStrengthLevel.L3_BASELINE_VERIFIER.value
    assert proof.proof_strength_label == ProofStrengthLabel.STRONG.value
    assert proof.verifier_independence == VerifierIndependence.STRONG.value


def test_baseline_failure_blocks_proven_when_tests_tampered(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_value():\n    assert True\n", encoding="utf-8"
    )

    def mutator(workspace: Path) -> None:
        (workspace / "tests" / "test_app.py").write_text(
            "def test_value():\n    assert True  # weakened\n", encoding="utf-8"
        )

    run_id, proof = run_and_prove(tmp_path, mutator, baseline_passes=False)
    assert proof.verdict is ProofVerdict.NOT_PROVEN
    assert proof.promotion == "BLOCKED"
    assert any("baseline verifier" in reason for reason in proof.reasons)
    assert proof.baseline_verifier == "FAIL"
    assert proof.verifier_independence == VerifierIndependence.REVIEW.value


def test_unmodified_verifier_files_still_run_baseline(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_value():\n    assert True\n", encoding="utf-8"
    )

    def mutator(workspace: Path) -> None:
        (workspace / "src" / "app.py").write_text("VALUE = 2\n", encoding="utf-8")

    run_id, proof = run_and_prove(tmp_path, mutator)
    assert proof.verdict is ProofVerdict.PROVEN
    assert proof.verifier_files_changed == 0
    assert proof.baseline_verifier == "PASS"
    assert proof.proof_strength == ProofStrengthLevel.L3_BASELINE_VERIFIER.value


def test_patch_added_verifier_file_removed_for_baseline(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")

    def mutator(workspace: Path) -> None:
        (workspace / "src" / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        (workspace / "tests").mkdir()
        (workspace / "tests" / "fake_extra_test.py").write_text(
            "def test_fake():\n    assert True\n", encoding="utf-8"
        )

    # Baseline is unavailable because the base had no verifier files; the
    # added test still must not be promoted silently (reported + NOT_PROVEN
    # because baseline cannot confirm).
    run_id, proof = run_and_prove(tmp_path, mutator)
    assert proof.baseline_available is False
    assert proof.verifier_files_changed == 0
    assert "tests/fake_extra_test.py" in proof.verifier_changes
    assert proof.verdict is ProofVerdict.NOT_PROVEN
    assert any("no baseline verifier" in reason for reason in proof.reasons)
