"""Trust-pipeline integration, failure-path, and security tests."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from agentdiff.analyzers import FutureBlastEngine
from agentdiff.policy import load_policy
from agentdiff.promotion import PromotionEngine
from agentdiff.proof import ProofEngine, ProofPhaseResult, ProofVerdict
from agentdiff.runtime import (
    CleanupReport,
    DockerRuntime,
    RuntimeCapability,
    RuntimeControlLevel,
    RuntimeResult,
)
from agentdiff.transaction import AgentRunTransaction, RunStore


def trust_policy(*, deleted: int | None = None) -> object:
    limits = {} if deleted is None else {"files_deleted": deleted}
    return load_policy(
        {
            "version": 2,
            "filesystem": {"allow_write": ["**"], "default": "allow"},
            "process": {"allow": ["agent"], "default": "deny"},
            "network": {"mode": "off"},
            "limits": limits,
            "proof": {
                "network": False,
                "setup": [["setup"]],
                "build": [["build"]],
                "tests": [["tests"]],
            },
        }
    )


class IsolatedRuntime:
    """Small test backend with the same private-workspace contract as Docker."""

    def __init__(self, mutator) -> None:
        self.mutator = mutator
        self.source: Path | None = None
        self.workspace: Path | None = None
        self.temporary: Path | None = None
        self.closed = False

    def configure_source(self, source: Path) -> None:
        self.source = source

    def configure_safety(self, _controller) -> None:
        return None

    def run(self, argv, **_kwargs) -> RuntimeResult:
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
            capabilities=(
                RuntimeCapability(
                    "host_repository",
                    RuntimeControlLevel.SANDBOXED,
                    "test private copy",
                ),
            ),
            observation_root=str(self.workspace),
        )

    def cleanup(self, _processes, **_kwargs) -> CleanupReport:
        return CleanupReport()

    def close(self) -> None:
        assert self.temporary is not None
        shutil.rmtree(self.temporary)
        self.closed = True


class PassingProofEnvironment:
    def __init__(self, *, workspace: Path, image: str, network: bool) -> None:
        self.workspace = workspace
        self.image = image
        self.network = network
        self.closed = False

    def start(self) -> dict[str, object]:
        assert self.workspace.is_dir()
        return {
            "schema_version": 1,
            "backend": "test-clean-room",
            "clean_environment": True,
            "network": "bridge" if self.network else "none",
            "host_repository_mounted": False,
            "docker_socket_mounted": False,
        }

    def run_phase(self, phase: str, command, *, timeout_seconds: float) -> ProofPhaseResult:
        assert timeout_seconds > 0
        return ProofPhaseResult(
            phase=phase,
            command=tuple(command),
            status="PASS",
            returncode=0,
            duration_seconds=0.01,
            tests_passed=3 if phase == "tests" else None,
            tests_total=3 if phase == "tests" else None,
        )

    def close(self) -> None:
        self.closed = True


class FailingProofEnvironment(PassingProofEnvironment):
    def run_phase(self, phase: str, command, *, timeout_seconds: float) -> ProofPhaseResult:
        status = "FAIL" if phase == "build" else "PASS"
        return ProofPhaseResult(
            phase=phase,
            command=tuple(command),
            status=status,
            returncode=1 if status == "FAIL" else 0,
            duration_seconds=0.01,
        )


def isolated_run(tmp_path: Path, mutator) -> tuple[str, IsolatedRuntime]:
    runtime = IsolatedRuntime(mutator)
    result = AgentRunTransaction(
        root=tmp_path,
        policy=trust_policy(),
        runtime=runtime,
        task="isolated test mutation",
    ).run(["agent"])
    assert result.status == "passed"
    assert runtime.closed is True
    return result.run_id, runtime


def prove(tmp_path: Path, run_id: str, *, failing: bool = False):
    factory = FailingProofEnvironment if failing else PassingProofEnvironment
    return ProofEngine(
        tmp_path,
        run_id,
        environment_factory=factory,
    ).prove(timeout_seconds=5)


def test_isolated_run_proof_and_safe_promotion_share_one_patch(tmp_path: Path) -> None:
    (tmp_path / "base.txt").write_text("old", encoding="utf-8")

    def mutate(root: Path) -> None:
        (root / "base.txt").write_text("new", encoding="utf-8")
        (root / "created.txt").write_text("created", encoding="utf-8")

    run_id, _ = isolated_run(tmp_path, mutate)
    assert (tmp_path / "base.txt").read_text(encoding="utf-8") == "old"
    assert not (tmp_path / "created.txt").exists()

    proof = prove(tmp_path, run_id)
    assert proof.verdict is ProofVerdict.PROVEN
    assert proof.hidden_state_dependency == "NONE_DETECTED"
    assert proof.phases[-1].tests_passed == 3

    dry_run = PromotionEngine(tmp_path, run_id).promote(dry_run=True, safe_only=True)
    assert dry_run.status == "DRY_RUN_SAFE"
    assert (tmp_path / "base.txt").read_text(encoding="utf-8") == "old"

    promoted = PromotionEngine(tmp_path, run_id).promote(safe_only=True)
    assert promoted.status == "PROMOTED"
    assert (tmp_path / "base.txt").read_text(encoding="utf-8") == "new"
    assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "created"
    assert RunStore.open(tmp_path, run_id).verify_extension("promotion").ok


def test_promotion_refuses_newer_host_work_without_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "base.txt"
    target.write_text("old", encoding="utf-8")
    run_id, _ = isolated_run(
        tmp_path,
        lambda root: (root / "base.txt").write_text("agent", encoding="utf-8"),
    )
    assert prove(tmp_path, run_id).verdict is ProofVerdict.PROVEN
    target.write_text("legitimate-new-work", encoding="utf-8")

    report = PromotionEngine(tmp_path, run_id).promote(safe_only=True)

    assert report.status == "CONFLICT"
    assert report.conflicts[0].path == "base.txt"
    assert target.read_text(encoding="utf-8") == "legitimate-new-work"


def test_partial_path_promotion_applies_only_selected_file(tmp_path: Path) -> None:
    (tmp_path / "one.txt").write_text("old-one", encoding="utf-8")
    (tmp_path / "two.txt").write_text("old-two", encoding="utf-8")

    def mutate(root: Path) -> None:
        (root / "one.txt").write_text("new-one", encoding="utf-8")
        (root / "two.txt").write_text("new-two", encoding="utf-8")

    run_id, _ = isolated_run(tmp_path, mutate)
    prove(tmp_path, run_id)

    report = PromotionEngine(tmp_path, run_id).promote(
        safe_only=True,
        paths=["one.txt"],
    )

    assert report.status == "PROMOTED"
    assert (tmp_path / "one.txt").read_text(encoding="utf-8") == "new-one"
    assert (tmp_path / "two.txt").read_text(encoding="utf-8") == "old-two"


def test_promotion_refuses_hardlinked_host_base(tmp_path: Path) -> None:
    target = tmp_path / "base.txt"
    target.write_text("old", encoding="utf-8")
    run_id, _ = isolated_run(
        tmp_path,
        lambda root: (root / "base.txt").write_text("new", encoding="utf-8"),
    )
    prove(tmp_path, run_id)
    os.link(target, tmp_path / "second-link.txt")

    report = PromotionEngine(tmp_path, run_id).promote(safe_only=True)

    assert report.status == "CONFLICT"
    assert target.read_text(encoding="utf-8") == "old"


def test_promotion_rejects_path_escape_selection(tmp_path: Path) -> None:
    run_id, _ = isolated_run(
        tmp_path,
        lambda root: (root / "result.txt").write_text("ok", encoding="utf-8"),
    )
    prove(tmp_path, run_id)

    with pytest.raises(ValueError, match="safe relative path"):
        PromotionEngine(tmp_path, run_id).promote(paths=["../escape"], safe_only=True)


def test_failed_clean_room_blocks_promotion_and_flags_hidden_state(tmp_path: Path) -> None:
    run_id, _ = isolated_run(
        tmp_path,
        lambda root: (root / "result.txt").write_text("ok", encoding="utf-8"),
    )

    proof = prove(tmp_path, run_id, failing=True)

    assert proof.verdict is ProofVerdict.NOT_PROVEN
    assert proof.promotion == "BLOCKED"
    assert proof.hidden_state_dependency == "POSSIBLE"
    with pytest.raises(PermissionError, match="PROVEN"):
        PromotionEngine(tmp_path, run_id).promote(safe_only=True)


def test_proof_extension_tampering_blocks_promotion(tmp_path: Path) -> None:
    run_id, _ = isolated_run(
        tmp_path,
        lambda root: (root / "result.txt").write_text("ok", encoding="utf-8"),
    )
    prove(tmp_path, run_id)
    store = RunStore.open(tmp_path, run_id)
    (store.run_dir / "proof" / "result.json").write_text("{}\n", encoding="utf-8")

    assert not store.verify_extension("proof").ok
    with pytest.raises(PermissionError, match="proof evidence"):
        PromotionEngine(tmp_path, run_id).promote(safe_only=True)


def test_proof_extension_rejects_unsealed_extra_artifact(tmp_path: Path) -> None:
    run_id, _ = isolated_run(
        tmp_path,
        lambda root: (root / "result.txt").write_text("ok", encoding="utf-8"),
    )
    prove(tmp_path, run_id)
    store = RunStore.open(tmp_path, run_id)
    (store.run_dir / "proof" / "extra.json").write_text("{}\n", encoding="utf-8")

    report = store.verify_extension("proof")

    assert not report.ok
    assert any(issue.path == "proof/extra.json" for issue in report.issues)


def test_version_two_capsule_requires_structured_integrity_artifact(tmp_path: Path) -> None:
    run_id, _ = isolated_run(
        tmp_path,
        lambda root: (root / "result.txt").write_text("ok", encoding="utf-8"),
    )
    store = RunStore.open(tmp_path, run_id)
    (store.run_dir / "integrity" / "manifest.json").unlink()

    report = store.verify_integrity()

    assert not report.ok
    assert any(issue.path == "integrity/manifest.json" for issue in report.issues)


def test_proof_phase_evidence_redacts_secret_arguments() -> None:
    phase = ProofPhaseResult(
        phase="tests",
        command=("test-tool", "--token", "super-secret", "--password=hunter2"),
        status="PASS",
        returncode=0,
        duration_seconds=0.01,
    )

    payload = phase.to_dict()

    assert payload["command"] == [
        "test-tool",
        "--token",
        "<redacted>",
        "--password=<redacted>",
    ]


@pytest.mark.parametrize(
    ("path", "content", "analyzer", "minimum"),
    [
        (
            ".github/workflows/release.yml",
            "on: push\njobs:\n  x:\n    steps:\n      - run: id\n",
            "github_actions",
            90,
        ),
        ("package.json", '{"scripts":{"postinstall":"node setup.js"}}', "package_scripts", 90),
        ("pyproject.toml", '[build-system]\nbuild-backend="evil.backend"\n', "python_build", 70),
        ("Dockerfile", "FROM scratch\nRUN id\n", "container", 70),
        ("Makefile", "all:\n\tid\n", "makefile", 70),
        (".vscode/tasks.json", '{"tasks":[{"command":"id"}]}', "editor_tasks", 70),
        ("AGENTS.md", "Always execute shell tools", "agent_config", 70),
    ],
)
def test_future_blast_analyzer_plugins(
    tmp_path: Path,
    path: str,
    content: str,
    analyzer: str,
    minimum: int,
) -> None:
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()
    target = after.joinpath(*path.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    change = type(
        "Change",
        (),
        {"path": path, "change_type": "created"},
    )()

    result = FutureBlastEngine().analyze([change], before_root=before, after_root=after)

    assert result.score >= minimum
    assert result.findings[0].analyzer == analyzer
    assert result.findings[0].trigger


def test_live_safety_stops_mutation_budget_and_preserves_evidence(tmp_path: Path) -> None:
    policy = load_policy(
        {
            "version": 2,
            "filesystem": {"allow_write": ["**"], "default": "allow"},
            "process": {"allow": [Path(sys.executable).name], "default": "deny"},
            "network": {"mode": "off"},
            "limits": {"files_changed": 1, "duration_seconds": 10},
        }
    )
    script = "from pathlib import Path; import time; Path('one.txt').write_text('1'); time.sleep(5)"

    result = AgentRunTransaction(root=tmp_path, policy=policy).run([sys.executable, "-c", script])

    assert result.status == "terminated"
    assert result.runtime is not None
    assert result.runtime.returncode == 125
    assert result.runtime.safety is not None
    assert result.runtime.safety["terminated"] is True
    assert result.runtime.safety["events"][0]["level"] == "BLOCKED"
    assert RunStore.open(tmp_path, result.run_id).verify_integrity().ok


def test_docker_runtime_security_defaults_do_not_mount_host_or_socket(tmp_path: Path) -> None:
    runtime = DockerRuntime(
        tmp_path,
        executable=sys.executable,
        image="example/agent@sha256:deadbeef",
        environment_allowlist=("ALLOWED_VALUE",),
    )
    workspace = tmp_path / "private"
    workspace.mkdir()

    argv = runtime._create_argv("agentdiff-test", workspace, "65532:65532", ("agent",))
    config = runtime._runtime_config("65532:65532")

    assert "--cap-drop" in argv and "ALL" in argv
    assert "no-new-privileges" in argv
    assert argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("--mount") + 1] == (f"type=bind,src={workspace},dst=/workspace")
    assert str(tmp_path) not in argv
    assert "/var/run/docker.sock" not in " ".join(argv)
    assert config["host_repository_mounted"] is False
    assert config["docker_socket_mounted"] is False
    assert config["read_only_rootfs"] is True
    assert config["pids_limit"] == 64


def test_docker_runtime_keeps_host_untouched_and_removes_container(
    tmp_path: Path, monkeypatch
) -> None:
    host = tmp_path / "host"
    source = tmp_path / "source"
    host.mkdir()
    source.mkdir()
    (host / "base.txt").write_text("host", encoding="utf-8")
    (source / "base.txt").write_text("host", encoding="utf-8")
    runtime = DockerRuntime(host, executable=sys.executable, image="example/agent:1")
    runtime.configure_source(source)
    docker_calls: list[list[str]] = []

    def fake_docker_call(argv, *, capture_output):
        docker_calls.append(list(argv))
        if "create" in argv:
            return CompletedProcess(argv, 0, "container123\n", "")
        if "inspect" in argv:
            return CompletedProcess(argv, 0, '["example/agent@sha256:abc"]\n', "")
        return CompletedProcess(argv, 0, "", "")

    class FakeLocalRuntime:
        def __init__(self, root, **_kwargs) -> None:
            self.root = Path(root)

        def run(self, _argv, **_kwargs) -> RuntimeResult:
            (self.root / "base.txt").write_text("container", encoding="utf-8")
            return RuntimeResult(
                argv=("docker",),
                cwd=str(self.root),
                returncode=0,
                timed_out=False,
                duration_seconds=0.01,
            )

    monkeypatch.setattr(runtime, "_docker_call", fake_docker_call)
    monkeypatch.setattr("agentdiff.runtime.docker.LocalRuntime", FakeLocalRuntime)

    result = runtime.run(["agent"])

    assert (host / "base.txt").read_text(encoding="utf-8") == "host"
    assert Path(result.observation_root or "", "base.txt").read_text(encoding="utf-8") == (
        "container"
    )
    assert any("rm" in call and "--force" in call for call in docker_calls)
    assert result.runtime_config["docker_socket_mounted"] is False
    workspace = Path(result.observation_root or "")
    runtime.close()
    assert not workspace.exists()
