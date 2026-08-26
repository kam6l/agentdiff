"""End-to-end rejection tests for untrusted migration workers."""

from __future__ import annotations

import errno
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from agentdiff.api import MigrationEngine, get_builtin_manifest
from agentdiff.api.generation_runtime import (
    DockerGeneratorRuntime,
    PrivateGenerationRuntime,
)
from agentdiff.api.generators import (
    CustomCommandGenerator,
    DeterministicASTGenerator,
    ExternalCodingAgentGenerator,
    GenerationResult,
)
from agentdiff.runtime import (
    CleanupReport,
    DockerLifecycleError,
    DockerRuntime,
    RuntimeResult,
)
from agentdiff.transaction import RunStore
from tests.fake_proof import fake_env_factory

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from agentdiff.api.generators import MigrationGenerator
    from agentdiff.api.models import MigrationPlan
    from agentdiff.runtime import OwnedProcess


_STRONG_RUNTIME_CONFIG: dict[str, Any] = {
    "image": "generator:test",
    "private_workspace": True,
    "host_repository_mounted": False,
    "docker_socket_mounted": False,
    "read_only_rootfs": True,
    "no_new_privileges": True,
    "network": "none",
    "cap_drop": ["ALL"],
    "user": "65532:65532",
    "cpus": 1.0,
    "memory": "512m",
    "pids_limit": 64,
    "environment_allowlist": [],
    "ephemeral_container": True,
    "control_timeout_seconds": 120.0,
}


class _FakeDockerBackend:
    """Test double for DockerRuntime that still uses a private observation copy."""

    def __init__(
        self,
        root: str | Path,
        *,
        mutator: Callable[[Path], None] | None = None,
        captured: dict[str, Any] | None = None,
        returncode: int = 0,
        timed_out: bool = False,
        runtime_config: dict[str, Any] | None = None,
        stdout_bytes: bytes = b"",
        stderr_bytes: bytes = b"",
        lifecycle_error_stage: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.root = Path(root)
        self.mutator = mutator
        self.captured = captured if captured is not None else {}
        self.captured["constructor"] = kwargs
        self.image = str(kwargs["image"])
        self.returncode = returncode
        self.timed_out = timed_out
        self.runtime_config = dict(runtime_config or _STRONG_RUNTIME_CONFIG)
        self.stdout_bytes = stdout_bytes
        self.stderr_bytes = stderr_bytes
        self.lifecycle_error_stage = lifecycle_error_stage
        self._source: Path | None = None
        self._temporary_root: Path | None = None

    def configure_source(self, source_dir: str | Path) -> None:
        self._source = Path(source_dir)

    def configure_safety(self, controller: Any) -> None:
        del controller

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float | None = None,
        stdin: Any = None,
        stdout: Any = None,
        stderr: Any = None,
    ) -> RuntimeResult:
        del stdin
        if self.lifecycle_error_stage is not None:
            raise DockerLifecycleError(self.lifecycle_error_stage)
        assert self._source is not None
        command = tuple(argv)
        self.captured["argv"] = command
        self.captured["timeout_seconds"] = timeout_seconds
        self._temporary_root = Path(tempfile.mkdtemp(prefix="agentdiff-test-docker-"))
        workspace = self._temporary_root / "workspace"
        shutil.copytree(self._source, workspace, symlinks=False)
        if self.mutator is not None:
            self.mutator(workspace)
        if stdout is not None and self.stdout_bytes:
            stdout.write(self.stdout_bytes)
            stdout.flush()
        if stderr is not None and self.stderr_bytes:
            stderr.write(self.stderr_bytes)
            stderr.flush()
        wrapper_argv = (
            "docker",
            "create",
            "--user",
            "65532:65532",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--network",
            "none",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=64m",
            "--cpus",
            "1.0",
            "--memory",
            "512m",
            "--pids-limit",
            "64",
            "--mount",
            f"type=bind,src={workspace},dst=/workspace",
            "--env",
            "HOME=/tmp",
            self.image,
            *command,
        )
        return RuntimeResult(
            argv=command,
            cwd="/workspace",
            returncode=self.returncode,
            timed_out=self.timed_out,
            duration_seconds=0.01,
            backend="docker",
            enforcement="isolated_private_workspace",
            wrapper_argv=wrapper_argv,
            image=self.image,
            runtime_config=self.runtime_config,
            observation_root=str(workspace),
        )

    def cleanup(
        self,
        processes: Iterable[OwnedProcess],
        *,
        grace_period_seconds: float = 1.0,
    ) -> CleanupReport:
        del processes, grace_period_seconds
        return CleanupReport()

    def close(self) -> None:
        if self._temporary_root is not None:
            shutil.rmtree(self._temporary_root)
            self._temporary_root = None


def _repository(tmp_path: Path) -> Path:
    source = tmp_path / "src"
    source.mkdir()
    (source / "app.py").write_text(
        """from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "hello"}],
)
print(response.choices[0].message.content)
""",
        encoding="utf-8",
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_smoke.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    return tmp_path


def _runtime_factory(
    root: Path,
    *,
    mutator: Callable[[Path], None] | None = None,
    captured: dict[str, Any] | None = None,
    returncode: int = 0,
    timed_out: bool = False,
    runtime_config: dict[str, Any] | None = None,
    stdout_bytes: bytes = b"",
    stderr_bytes: bytes = b"",
    lifecycle_error_stage: str | None = None,
    output_limit_bytes_per_stream: int = 1_000_000,
    execution_timeout_seconds: float = 900.0,
    control_timeout_seconds: float = 120.0,
) -> Callable[[MigrationPlan, MigrationGenerator], DockerGeneratorRuntime]:
    def create(
        plan: MigrationPlan,
        generator: MigrationGenerator,
    ) -> DockerGeneratorRuntime:
        assert isinstance(generator, CustomCommandGenerator)

        def docker_factory(docker_root: str | Path, **kwargs: Any) -> _FakeDockerBackend:
            return _FakeDockerBackend(
                docker_root,
                mutator=mutator,
                captured=captured,
                returncode=returncode,
                timed_out=timed_out,
                runtime_config=runtime_config,
                stdout_bytes=stdout_bytes,
                stderr_bytes=stderr_bytes,
                lifecycle_error_stage=lifecycle_error_stage,
                **kwargs,
            )

        return DockerGeneratorRuntime(
            root,
            plan,
            generator,
            image="generator:test",
            output_limit_bytes_per_stream=output_limit_bytes_per_stream,
            execution_timeout_seconds=execution_timeout_seconds,
            control_timeout_seconds=control_timeout_seconds,
            docker_runtime_factory=docker_factory,
        )

    return create


def _plan(root: Path) -> tuple[MigrationEngine, MigrationPlan]:
    engine = MigrationEngine(
        root,
        manifest=get_builtin_manifest("openai", "chat_to_responses"),
    )
    usages, impact = engine.scan_and_match()
    return engine, engine.create_plan(usages, impact)


def test_successful_worker_that_changes_nothing_is_not_proven(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    captured: dict[str, Any] = {}
    command = ("agent-worker", "--prompt", "leave unchanged; $(touch host)")
    engine = MigrationEngine(
        root,
        manifest=get_builtin_manifest("openai", "chat_to_responses"),
        generator=ExternalCodingAgentGenerator(command, name="external-agent"),
        generator_runtime_factory=_runtime_factory(root, captured=captured),
        proof_environment_factory=fake_env_factory(),
    )

    result = engine.run()

    assert captured["argv"] == command
    assert result.proof_verdict == "NOT_PROVEN"
    assert result.certificate is not None
    assert result.certificate.verified is False
    assert result.errors[0] == "EXPECTED FILE NOT MODIFIED: src/app.py"


def test_unexpected_workflow_change_is_rejected(tmp_path: Path) -> None:
    root = _repository(tmp_path)

    def write_workflow(workspace: Path) -> None:
        workflow = workspace / ".github" / "workflows" / "deploy.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("unsafe: true\n", encoding="utf-8")

    engine = MigrationEngine(
        root,
        manifest=get_builtin_manifest("openai", "chat_to_responses"),
        generator=CustomCommandGenerator(("agent-worker", "migrate")),
        generator_runtime_factory=_runtime_factory(root, mutator=write_workflow),
        proof_environment_factory=fake_env_factory(),
    )

    result = engine.run()

    assert result.proof_verdict == "NOT_PROVEN"
    assert result.certificate is not None
    assert result.certificate.policy_result == "DENY"
    assert result.certificate.verified is False
    assert result.unexpected_files == (".github/workflows/deploy.yml",)
    assert any(error.startswith("UNEXPECTED FILE MODIFICATION") for error in result.errors)
    assert not (root / ".github" / "workflows" / "deploy.yml").exists()


def test_custom_generator_has_no_host_execution_method(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    _, plan = _plan(root)
    marker = tmp_path / "host-executed"
    generator = CustomCommandGenerator(
        (
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).touch()",
        )
    )

    assert not hasattr(generator, "generate")
    with pytest.raises(TypeError, match="only DeterministicASTGenerator"):
        PrivateGenerationRuntime(plan, generator)  # type: ignore[arg-type]

    assert not marker.exists()


def test_deterministic_subclass_cannot_gain_in_process_execution(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    marker = tmp_path / "subclass-host-executed"

    class UntrustedSubclass(DeterministicASTGenerator):
        def generate(self, plan: MigrationPlan, workspace: Path) -> GenerationResult:
            del plan, workspace
            marker.touch()
            return GenerationResult(
                success=True,
                generator=self.name,
                strategy=self.strategy,
            )

    engine = MigrationEngine(
        root,
        manifest=get_builtin_manifest("openai", "chat_to_responses"),
        generator=UntrustedSubclass(),
    )

    with pytest.raises(TypeError, match="explicit isolated runtime factory"):
        engine.run()

    assert not marker.exists()


def test_docker_runtime_preserves_exact_argv_and_requires_security_controls(
    tmp_path: Path,
) -> None:
    root = _repository(tmp_path)
    _, plan = _plan(root)
    command = (
        "agent-worker",
        "--prompt",
        "two words; $(uname)",
        "--privileged",
        "/var/run/docker.sock",
    )
    generator = CustomCommandGenerator(command)
    captured: dict[str, Any] = {}
    runtime = _runtime_factory(root, captured=captured)(plan, generator)
    runtime.configure_source(root)

    result = runtime.run(command, timeout_seconds=17)
    runtime.close()

    assert result.argv == command
    assert captured["argv"] == command
    assert captured["constructor"] == {
        "image": "generator:test",
        "network": "none",
        "environment_allowlist": (),
        "control_timeout_seconds": 120.0,
    }
    assert captured["timeout_seconds"] == 17
    assert runtime.generation_result == GenerationResult(
        success=True,
        generator="custom-command",
        strategy=generator.strategy,
    )


def test_docker_runtime_rejects_weakened_isolation_evidence(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    _, plan = _plan(root)
    generator = CustomCommandGenerator(("agent-worker",))
    weakened = {**_STRONG_RUNTIME_CONFIG, "network": "bridge"}
    runtime = _runtime_factory(root, runtime_config=weakened)(plan, generator)
    runtime.configure_source(root)

    with pytest.raises(OSError, match="required isolation"):
        runtime.run(generator.argv)
    runtime.close()

    assert runtime.generation_result is None


def test_generator_image_cannot_inject_docker_options(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    _, plan = _plan(root)
    generator = CustomCommandGenerator(("agent-worker",))

    with pytest.raises(ValueError, match="cannot be an option"):
        DockerGeneratorRuntime(root, plan, generator, image="--privileged")


def test_generator_output_capture_is_bounded_and_fails_closed(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    _, plan = _plan(root)
    generator = CustomCommandGenerator(("agent-worker",))
    captured: dict[str, Any] = {}
    stdout_bytes = b"x" * 20
    stderr_bytes = b"error"
    runtime = _runtime_factory(
        root,
        captured=captured,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        output_limit_bytes_per_stream=8,
    )(plan, generator)
    runtime.configure_source(root)

    result = runtime.run(generator.argv, timeout_seconds=2_000)
    runtime.close()

    assert result.runtime_config is not None
    output = result.runtime_config["generator_output"]
    assert result.returncode == 125
    assert captured["timeout_seconds"] == 900.0
    assert output == {
        "limit_bytes_per_stream": 8,
        "limited": True,
        "stdout": {
            "total_bytes": 20,
            "captured_bytes": 8,
            "sha256": hashlib.sha256(stdout_bytes).hexdigest(),
            "limited": True,
            "complete": True,
        },
        "stderr": {
            "total_bytes": 5,
            "captured_bytes": 5,
            "sha256": hashlib.sha256(stderr_bytes).hexdigest(),
            "limited": False,
            "complete": True,
        },
    }
    assert runtime.generation_result is not None
    assert runtime.generation_result.errors == (
        "Docker generator output exceeded the safety limit",
    )


def test_output_limit_is_preserved_as_migration_error_evidence(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    engine = MigrationEngine(
        root,
        manifest=get_builtin_manifest("openai", "chat_to_responses"),
        generator=CustomCommandGenerator(("agent-worker",)),
        generator_runtime_factory=_runtime_factory(
            root,
            stdout_bytes=b"unbounded output",
            output_limit_bytes_per_stream=4,
        ),
        proof_environment_factory=fake_env_factory(),
    )

    result = engine.run()

    assert result.proof_verdict == "NOT_PROVEN"
    assert "Docker generator output exceeded the safety limit" in result.errors
    runtime_evidence = RunStore.open(root, result.run_id).read_json("runtime.json")
    assert runtime_evidence["returncode"] == 125
    assert runtime_evidence["runtime_config"]["generator_output"]["limited"] is True


def test_docker_control_calls_have_an_explicit_wall_clock_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed["argv"] = argv
        observed["timeout"] = kwargs["timeout"]
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("agentdiff.runtime.docker.subprocess.run", fake_run)
    runtime = DockerRuntime(
        tmp_path,
        executable=sys.executable,
        image="generator:test",
        control_timeout_seconds=3.5,
    )

    runtime._docker_call([runtime.executable, "version"], capture_output=True)

    assert observed["timeout"] == 3.5


def test_docker_create_and_inspect_timeouts_have_deterministic_stages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = DockerRuntime(
        tmp_path,
        executable=sys.executable,
        image="generator:test",
        control_timeout_seconds=0.01,
    )
    runtime.configure_source(tmp_path)

    def time_out(argv: Sequence[str], *, capture_output: bool) -> Any:
        del capture_output
        raise subprocess.TimeoutExpired(argv, 0.01)

    monkeypatch.setattr(runtime, "_docker_call", time_out)

    with pytest.raises(DockerLifecycleError) as create_error:
        runtime.run(("agent-worker",), timeout_seconds=1)
    assert create_error.value.stage == "create"
    runtime.close()

    with pytest.raises(DockerLifecycleError) as inspect_error:
        runtime._image_digest()
    assert inspect_error.value.stage == "inspect"


def test_lifecycle_timeout_is_preserved_as_migration_error_evidence(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    engine = MigrationEngine(
        root,
        manifest=get_builtin_manifest("openai", "chat_to_responses"),
        generator=CustomCommandGenerator(("agent-worker",)),
        generator_runtime_factory=_runtime_factory(root, lifecycle_error_stage="create"),
        proof_environment_factory=fake_env_factory(),
    )

    result = engine.run()

    assert result.proof_verdict == "NOT_PROVEN"
    assert "Docker generator create timed out" in result.errors
    runtime_evidence = RunStore.open(root, result.run_id).read_json("runtime.json")
    assert runtime_evidence["execution_error"] == {
        "type": "DockerLifecycleError",
        "errno": errno.ETIMEDOUT,
    }


def test_cli_exposes_generator_image_for_api_and_fleet_migrations() -> None:
    from agentdiff.cli import build_parser

    parser = build_parser()
    api_args = parser.parse_args(
        [
            "api",
            "migrate",
            "--change",
            "chat_to_responses",
            "--generator",
            "command",
            "--generator-argv",
            "agent-worker",
            "--generator-image",
            "registry.example/worker@sha256:abc",
        ]
    )
    fleet_args = parser.parse_args(
        [
            "fleet",
            "migrate",
            "--config",
            "fleet.yml",
            "--generator-image",
            "registry.example/worker:1",
        ]
    )

    assert api_args.generator_image == "registry.example/worker@sha256:abc"
    assert fleet_args.generator_image == "registry.example/worker:1"


def test_docker_timeout_is_a_failed_generation(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    _, plan = _plan(root)
    generator = CustomCommandGenerator(("agent-worker",))
    runtime = _runtime_factory(root, returncode=124, timed_out=True)(plan, generator)
    runtime.configure_source(root)

    result = runtime.run(generator.argv, timeout_seconds=0.01)
    runtime.close()

    assert result.timed_out is True
    assert runtime.generation_result is not None
    assert runtime.generation_result.success is False
    assert runtime.generation_result.errors == ("Docker generator start/attach timed out",)


@pytest.mark.parametrize(
    "generator_class",
    [CustomCommandGenerator, ExternalCodingAgentGenerator],
)
def test_unavailable_docker_fails_closed_without_host_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    generator_class: type[CustomCommandGenerator],
) -> None:
    root = _repository(tmp_path)
    marker = tmp_path / "host-fallback"
    command = (
        sys.executable,
        "-c",
        f"from pathlib import Path; Path({str(marker)!r}).touch()",
    )
    monkeypatch.setattr("agentdiff.runtime.docker.shutil.which", lambda _executable: None)
    engine = MigrationEngine(
        root,
        manifest=get_builtin_manifest("openai", "chat_to_responses"),
        generator=generator_class(command),
    )

    with pytest.raises(FileNotFoundError, match="Docker executable not found"):
        engine.run()

    assert not marker.exists()
