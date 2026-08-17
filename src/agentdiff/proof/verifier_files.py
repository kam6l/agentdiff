"""Deterministic classification of verifier-related files.

A verifier-related file is any file whose content can change what a
verification command executes or how it is interpreted: test sources,
fixtures, test runners, package/build manifests, lockfiles, CI workflows,
and tool configuration. The classifier is deliberately conservative
(inclusion-biased): under-inclusion would let an agent silently weaken the
verifier, while over-inclusion only reports a change that the baseline
verifier must then independently confirm.

The classifier never decides intent. It feeds a mutation *report*; policy
and proof verdicts remain deterministic.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Iterable

# Directories that contain test sources or fixtures anywhere in the tree.
_VERIFIER_DIR_PREFIXES = ("tests/", "test/", "__tests__/")

# Well-known CI workflow locations.
_VERIFIER_PATH_PREFIXES = (".github/", ".circleci/", ".travis.yml", ".gitlab-ci.yml")

# Exact configuration/test-runner filenames.
_VERIFIER_BASENAMES = frozenset(
    {
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
        "Pipfile",
        "Pipfile.lock",
        "pyproject.toml",
    }
)

# Glob patterns for runner configs and dependency manifests.
_VERIFIER_PATTERNS = (
    "vitest.config.*",
    "jest.config.*",
    "playwright.config.*",
    "karma.conf.*",
    "requirements*.txt",
    "requirements*.in",
)

# Common test-file naming conventions (path-level, not content-level).
_TEST_FILE_PATTERNS = (
    "test_*.py",
    "*_test.py",
    "*.test.js",
    "*.test.jsx",
    "*.test.ts",
    "*.test.tsx",
    "*.spec.js",
    "*.spec.jsx",
    "*.spec.ts",
    "*.spec.tsx",
    "*_test.go",
    "*.test.rs",
)


def is_verifier_related(relative_path: str) -> bool:
    """Return whether ``relative_path`` can influence verification behavior."""
    path = relative_path.replace("\\", "/")
    if not path or path.startswith("/") or ".." in path.split("/"):
        return False
    basename = path.rsplit("/", 1)[-1]
    if basename in _VERIFIER_BASENAMES:
        return True
    if any(path.startswith(prefix) for prefix in _VERIFIER_DIR_PREFIXES):
        return True
    if any(path.startswith(prefix) for prefix in _VERIFIER_PATH_PREFIXES):
        return True
    if any(fnmatch.fnmatchcase(basename, pattern) for pattern in _VERIFIER_PATTERNS):
        return True
    if any(fnmatch.fnmatchcase(basename, pattern) for pattern in _TEST_FILE_PATTERNS):
        return True
    return False


@dataclass(frozen=True, slots=True)
class VerifierMutationReport:
    """Deterministic summary of patch changes to verifier-related files."""

    existing_changed: tuple[str, ...] = ()
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()

    @property
    def modified_count(self) -> int:
        return len(self.existing_changed)

    @property
    def total_changes(self) -> int:
        return self.modified_count + len(self.added) + len(self.removed)

    @property
    def any_modification(self) -> bool:
        return self.total_changes > 0

    def to_dict(self) -> dict[str, object]:
        return {
            "existing_changed": list(self.existing_changed),
            "added": list(self.added),
            "removed": list(self.removed),
            "modified_count": self.modified_count,
            "total_changes": self.total_changes,
        }


def analyze_verifier_mutations(
    changed_paths: Iterable[tuple[str, str]],
) -> VerifierMutationReport:
    """Classify ``(path, change_type)`` pairs against verifier-related files."""
    existing_changed: list[str] = []
    added: list[str] = []
    removed: list[str] = []
    for path, change_type in changed_paths:
        if not is_verifier_related(path):
            continue
        if change_type == "modified":
            existing_changed.append(path)
        elif change_type == "created":
            added.append(path)
        elif change_type == "deleted":
            removed.append(path)
    return VerifierMutationReport(
        existing_changed=tuple(sorted(existing_changed)),
        added=tuple(sorted(added)),
        removed=tuple(sorted(removed)),
    )
