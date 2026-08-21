"""Publish the exact proven migration patch as a GitHub pull request."""

from __future__ import annotations

import hashlib
import re
import subprocess  # nosec B404 -- all commands use exact argv without a shell
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from agentdiff.api.certificate import CertificateStatus, verify_certificate
from agentdiff.evidence import PatchBundle
from agentdiff.transaction.store import RunStore

if TYPE_CHECKING:
    from agentdiff.api.models import MigrationResult


_BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,119}$")


@dataclass(frozen=True, slots=True)
class PullRequestResult:
    url: str
    branch: str
    commit_sha: str
    base_sha: str
    patch_digest: str

    def to_dict(self) -> dict[str, str]:
        return {
            "url": self.url,
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "base_sha": self.base_sha,
            "patch_digest": self.patch_digest,
        }


Runner = Callable[..., subprocess.CompletedProcess[str]]


class VerifiedPRPublisher:
    """Create a branch and PR only from sealed, still-current proven evidence."""

    def __init__(self, root: str | Path, *, runner: Runner = subprocess.run) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        self.runner = runner

    def publish(
        self,
        result: MigrationResult,
        certificate_path: str | Path,
        *,
        base_branch: str,
        branch: str | None = None,
        draft: bool = False,
    ) -> PullRequestResult:
        certificate = result.certificate
        if (
            result.proof_verdict != "PROVEN"
            or certificate is None
            or not certificate.verified
            or certificate.final_verdict != "PROVEN"
        ):
            raise ValueError("PR creation requires a PROVEN migration")
        status, reason = verify_certificate(certificate_path, root=self.root)
        if status is not CertificateStatus.VALID:
            raise ValueError(f"certificate is not current: {status.value}: {reason}")
        base_sha = self._git("rev-parse", "HEAD").stdout.strip()
        if base_sha != certificate.repository_base_sha:
            raise ValueError("repository base SHA changed after proof; re-run verification")
        self._require_clean_tracked_worktree()

        selected_branch = branch or (
            f"agentdiff/{certificate.provider}-{certificate.change_id}-{base_sha[:8]}"
        )
        if not _BRANCH_PATTERN.fullmatch(selected_branch) or ".." in selected_branch:
            raise ValueError("invalid PR branch name")
        if (
            self._git(
                "show-ref", "--verify", f"refs/heads/{selected_branch}", check=False
            ).returncode
            == 0
        ):
            raise ValueError(f"local branch already exists: {selected_branch}")
        self._git("remote", "get-url", "origin")

        store = RunStore.open(self.root, certificate.capsule_id)
        bundle = PatchBundle(store)
        with tempfile.TemporaryDirectory(prefix="agentdiff-pr-") as temporary:
            worktree = Path(temporary) / "worktree"
            self._git("worktree", "add", "--detach", str(worktree), base_sha)
            try:
                self._git_at(worktree, "switch", "-c", selected_branch)
                self._verify_base(worktree, bundle)
                bundle.apply(worktree)
                self._verify_result(worktree, bundle)
                expected = tuple(entry.path for entry in bundle.manifest.entries)
                self._git_at(worktree, "add", "--all", "--", *expected)
                staged = tuple(
                    line
                    for line in self._git_at(
                        worktree, "diff", "--cached", "--name-only"
                    ).stdout.splitlines()
                    if line
                )
                if set(staged) != set(expected):
                    raise RuntimeError("staged PR patch differs from sealed patch paths")
                title = f"Migrate {certificate.provider}: {certificate.change_id}"
                self._git_at(
                    worktree,
                    "-c",
                    "user.name=AgentDiff",
                    "-c",
                    "user.email=agentdiff@users.noreply.github.com",
                    "commit",
                    "-m",
                    title,
                )
                commit_sha = self._git_at(worktree, "rev-parse", "HEAD").stdout.strip()
                self._git_at(worktree, "push", "--set-upstream", "origin", selected_branch)
                body = build_verified_pr_body(result)
                command = [
                    "gh",
                    "pr",
                    "create",
                    "--base",
                    base_branch,
                    "--head",
                    selected_branch,
                    "--title",
                    title,
                    "--body",
                    body,
                ]
                if draft:
                    command.append("--draft")
                url = self._run(command, cwd=worktree).stdout.strip().splitlines()[-1]
            finally:
                self._git("worktree", "remove", str(worktree), check=False)
        return PullRequestResult(
            url=url,
            branch=selected_branch,
            commit_sha=commit_sha,
            base_sha=base_sha,
            patch_digest=bundle.manifest.digest,
        )

    def _require_clean_tracked_worktree(self) -> None:
        if self._git("diff", "--quiet", check=False).returncode != 0:
            raise ValueError("tracked worktree changes must be committed before --open-pr")
        if self._git("diff", "--cached", "--quiet", check=False).returncode != 0:
            raise ValueError("staged changes must be committed before --open-pr")

    def _verify_base(self, worktree: Path, bundle: PatchBundle) -> None:
        for entry in bundle.manifest.entries:
            target = worktree.joinpath(*entry.path.split("/"))
            if entry.base_sha256 is None:
                if target.exists() or target.is_symlink():
                    raise RuntimeError(f"created path already exists at proven base: {entry.path}")
            elif not target.is_file() or _sha256(target) != entry.base_sha256:
                raise RuntimeError(f"base file differs from sealed evidence: {entry.path}")

    def _verify_result(self, worktree: Path, bundle: PatchBundle) -> None:
        for entry in bundle.manifest.entries:
            target = worktree.joinpath(*entry.path.split("/"))
            if entry.result_sha256 is None:
                if target.exists() or target.is_symlink():
                    raise RuntimeError(f"deleted path still exists: {entry.path}")
            elif not target.is_file() or _sha256(target) != entry.result_sha256:
                raise RuntimeError(f"PR file differs from sealed patch: {entry.path}")

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self._run(["git", *args], cwd=self.root, check=check)

    def _git_at(
        self, cwd: Path, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return self._run(["git", *args], cwd=cwd, check=check)

    def _run(
        self, command: list[str], *, cwd: Path, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        try:
            completed = self.runner(
                command,
                cwd=cwd,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError(f"command unavailable: {Path(command[0]).name}") from error
        if check and completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()[-1000:]
            raise RuntimeError(f"{Path(command[0]).name} failed: {detail or completed.returncode}")
        return completed


def build_verified_pr_body(result: MigrationResult) -> str:
    certificate = result.certificate
    if certificate is None:
        raise ValueError("migration certificate is required")
    return "\n".join(
        [
            "## AGENTDIFF VERIFIED MIGRATION",
            "",
            f"- Provider: `{certificate.provider}`",
            f"- Change: `{certificate.change_id}`",
            f"- Affected usages: `{certificate.affected_usages}`",
            f"- Affected files: `{len(certificate.actual_modified_files)}`",
            f"- Unexpected files: `{len(certificate.unexpected_files)}`",
            f"- Migration strategy: `{certificate.migration_strategy}`",
            (
                f"- Blast radius: `{certificate.blast_radius_level}` "
                f"({certificate.blast_radius_score}/100)"
            ),
            f"- Policy: `{certificate.policy_result}`",
            f"- Verification: `{certificate.verification_level.value.upper()}`",
            f"- Build: `{certificate.build_result}`",
            f"- Type check: `{certificate.type_check_result}`",
            f"- Full tests: `{certificate.full_test_result}`",
            f"- Proof: `{certificate.final_verdict}`",
            f"- Patch digest: `{certificate.migration_digest}`",
            f"- Certificate: `{certificate.certificate_id}`",
            f"- Evidence capsule: `{certificate.capsule_id}`",
            "",
            "**Final result: PROVEN**",
            "",
            "The branch was created from the exact sealed patch. AgentDiff never auto-merges.",
        ]
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
