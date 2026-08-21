"""Model-agnostic migration generators.

Generators are workers. Their output is always treated as an untrusted patch;
only the AgentDiff trust pipeline can decide whether that patch is proven.
"""

from __future__ import annotations

import subprocess  # nosec B404 -- custom generators use exact argv without a shell
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from agentdiff.api.models import MigrationStatus, MigrationStrategy
from agentdiff.api.transforms import TransformContext, get_transform

if TYPE_CHECKING:
    from agentdiff.api.models import MigrationPlan


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Result produced by an untrusted migration worker."""

    success: bool
    generator: str
    strategy: MigrationStrategy
    modified_files: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    returncode: int = 0


class MigrationGenerator(ABC):
    """Interface implemented by deterministic, agent, and custom workers."""

    name: str
    strategy: MigrationStrategy

    @property
    def command_label(self) -> str:
        """Stable policy subject recorded for the generator transaction."""

        return self.name

    @abstractmethod
    def generate(self, plan: MigrationPlan, workspace: Path) -> GenerationResult:
        """Generate a patch inside a private workspace."""


class DeterministicASTGenerator(MigrationGenerator):
    """Apply registered AST transforms without model calls."""

    name = "agentdiff-deterministic-ast"
    strategy = MigrationStrategy.AST_TRANSFORM

    def generate(self, plan: MigrationPlan, workspace: Path) -> GenerationResult:
        review_steps = [step for step in plan.steps if step.status is MigrationStatus.NEEDS_REVIEW]
        if review_steps:
            return GenerationResult(
                success=False,
                generator=self.name,
                strategy=self.strategy,
                errors=tuple(f"{step.step_id}: {step.description}" for step in review_steps),
                returncode=2,
            )

        steps_by_file: dict[str, list[str]] = {}
        for step in plan.steps:
            if step.transform_id is None:
                return GenerationResult(
                    success=False,
                    generator=self.name,
                    strategy=self.strategy,
                    errors=(f"{step.step_id}: no deterministic transform is available",),
                    returncode=2,
                )
            transform_ids = steps_by_file.setdefault(step.filepath, [])
            if step.transform_id not in transform_ids:
                transform_ids.append(step.transform_id)

        staged: dict[str, str] = {}
        errors: list[str] = []
        for filepath, transform_ids in sorted(steps_by_file.items()):
            source_path = workspace.joinpath(*filepath.split("/"))
            if not source_path.is_file():
                errors.append(f"source file not found: {filepath}")
                continue
            source = source_path.read_text(encoding="utf-8")
            original = source
            file_usages = tuple(
                usage for usage in plan.affected_usages if usage.filepath == filepath
            )
            for transform_id in transform_ids:
                transform = get_transform(transform_id)
                if transform is None:
                    errors.append(f"transform not registered: {transform_id}")
                    break
                usage = next(
                    (
                        candidate
                        for candidate in file_usages
                        if candidate.symbol in transform.affected_symbols
                    ),
                    None,
                )
                if usage is None:
                    errors.append(f"no matching usage for {transform_id} in {filepath}")
                    break
                context = TransformContext(
                    usage=usage,
                    source_code=source,
                    filepath=filepath,
                    manifest=plan.manifest,
                    all_usages=plan.affected_usages,
                )
                if not transform.can_transform(context):
                    errors.append(f"transform refused unsupported shape in {filepath}")
                    break
                result = transform.transform(context)
                if not result.success:
                    errors.extend(f"{filepath}: {change}" for change in result.changes)
                    break
                source = result.modified_code
            if source != original:
                staged[filepath] = source

        if errors:
            return GenerationResult(
                success=False,
                generator=self.name,
                strategy=self.strategy,
                errors=tuple(errors),
                returncode=1,
            )
        if set(staged) != set(plan.affected_files):
            missing = sorted(set(plan.affected_files) - set(staged))
            return GenerationResult(
                success=False,
                generator=self.name,
                strategy=self.strategy,
                errors=(f"generator produced no change for expected files: {', '.join(missing)}",),
                returncode=1,
            )

        for filepath, content in staged.items():
            workspace.joinpath(*filepath.split("/")).write_text(content + "\n", encoding="utf-8")
        return GenerationResult(
            success=True,
            generator=self.name,
            strategy=self.strategy,
            modified_files=tuple(sorted(staged)),
        )


class CustomCommandGenerator(MigrationGenerator):
    """Run a user-supplied exact argv sequence in the private workspace."""

    strategy = MigrationStrategy.CODING_AGENT

    def __init__(self, argv: tuple[str, ...], *, name: str = "custom-command") -> None:
        if not argv or any(not argument or "\x00" in argument for argument in argv):
            raise ValueError("custom generator argv must contain valid arguments")
        self.argv = argv
        self.name = name

    @property
    def command_label(self) -> str:
        return Path(self.argv[0]).name

    def generate(self, plan: MigrationPlan, workspace: Path) -> GenerationResult:
        del plan
        try:
            completed = subprocess.run(  # nosec B603
                self.argv,
                cwd=workspace,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=900,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return GenerationResult(
                success=False,
                generator=self.name,
                strategy=self.strategy,
                errors=(f"custom generator failed: {type(error).__name__}",),
                returncode=1,
            )
        detail = (completed.stderr or completed.stdout)[-1000:].strip()
        return GenerationResult(
            success=completed.returncode == 0,
            generator=self.name,
            strategy=self.strategy,
            errors=() if completed.returncode == 0 else (detail or "custom generator failed",),
            returncode=completed.returncode,
        )


class ExternalCodingAgentGenerator(CustomCommandGenerator):
    """Named custom-command worker for Codex, Claude, Gemini, or another agent."""
