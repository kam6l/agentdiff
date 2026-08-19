"""Deterministic repository inspection for the trust compiler.

Inspection is pure file-system observation: it lists files, reads bounded
text files, detects languages/package managers/test tooling/build tooling/
monorepo layout/CI/CODEOWNERS/agent configs, and hashes lockfiles. It never
executes commands and never consults a model.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess  # nosec B404 -- git rev-parse with fixed argv only
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

_SCAN_IGNORED_NAMES = frozenset(
    {
        ".agentdiff",
        "agentdiff.yaml",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
        ".next",
        ".turbo",
        "target",
        ".idea",
        ".vscode",
        ".DS_Store",
    }
)
_MAX_TEXT_BYTES = 256 * 1024
_MAX_LOCKFILE_BYTES = 16 * 1024 * 1024

_LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".swift": "swift",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".vue": "vue",
    ".svelte": "svelte",
    ".scala": "scala",
    ".ex": "elixir",
    ".exs": "elixir",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".tf": "terraform",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "css",
    ".less": "css",
}

_PYTHON_CONFIG_NAMES = frozenset(
    {"pyproject.toml", "setup.py", "setup.cfg", "tox.ini", "pytest.ini", "conftest.py"}
)
_NODE_CONFIG_NAMES = frozenset(
    {"package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"}
)
_GO_CONFIG_NAMES = frozenset({"go.mod", "go.sum", "go.work"})
_RUST_CONFIG_NAMES = frozenset({"Cargo.toml", "Cargo.lock"})
_JAVA_CONFIG_NAMES = frozenset({"pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle"})
_RUBY_CONFIG_NAMES = frozenset({"Gemfile", "Gemfile.lock"})
_PHP_CONFIG_NAMES = frozenset({"composer.json", "composer.lock"})
_ELIXIR_CONFIG_NAMES = frozenset({"mix.exs", "mix.lock"})

_AGENT_CONFIG_PATHS = frozenset(
    {
        "agents.md",
        "claude.md",
        ".github/copilot-instructions.md",
        ".github/copilot-instructions.md5",
        ".cursor/rules",
        ".gemini/instructions.md",
        ".copilot/instructions.md",
    }
)

_SECURITY_PATH_PARTS = frozenset({".aws", ".ssh", ".kube", "credentials", "secrets"})
_SECURITY_FILE_NAMES = frozenset(
    {"authorized_keys", "credentials", "id_dsa", "id_ed25519", "id_rsa", "known_hosts"}
)

_WORKSPACE_MANIFESTS = frozenset({"pnpm-workspace.yaml", "nx.json", "go.work", "lerna.json"})

# Deterministic, repository-derived proof phases (setup/build/tests) per manager.
# These mirror the trust hierarchy in agentdiff.proof.plan but are compiled once
# at bootstrap time into the canonical proof plan.
_MANAGER_PROOF_COMMANDS: dict[str, dict[str, list[list[str]]]] = {
    "uv": {
        "setup": [["uv", "sync", "--frozen", "--no-cache"]],
        "build": [["uv", "build"]],
        "tests": [["uv", "run", "pytest", "-q"]],
    },
    "poetry": {
        "setup": [["poetry", "install", "--no-root"]],
        "build": [["poetry", "build"]],
        "tests": [["poetry", "run", "pytest", "-q"]],
    },
    "pip": {
        "setup": [
            ["python", "-m", "venv", ".agentdiff-proof/venv"],
            [
                ".agentdiff-proof/venv/bin/python",
                "-m",
                "pip",
                "install",
                "--no-cache-dir",
                "-e",
                ".",
            ],
        ],
        "build": [[".agentdiff-proof/venv/bin/python", "-m", "compileall", "-q", "src"]],
        "tests": [[".agentdiff-proof/venv/bin/python", "-m", "pytest", "-q"]],
    },
    "npm": {
        "setup": [["npm", "ci"]],
        "build": [["npm", "run", "build", "--if-present"]],
        "tests": [["npm", "test"]],
    },
    "pnpm": {
        "setup": [["pnpm", "install", "--frozen-lockfile"]],
        "build": [["pnpm", "run", "build", "--if-present"]],
        "tests": [["pnpm", "test"]],
    },
    "yarn": {
        "setup": [["yarn", "install", "--frozen-lockfile"]],
        "build": [["yarn", "run", "build", "--if-present"]],
        "tests": [["yarn", "test"]],
    },
    "go": {
        "setup": [],
        "build": [["go", "build", "./..."]],
        "tests": [["go", "test", "./..."]],
    },
    "cargo": {
        "setup": [],
        "build": [["cargo", "build", "--locked"]],
        "tests": [["cargo", "test", "--locked"]],
    },
    "maven": {
        "setup": [],
        "build": [["mvn", "-q", "-DskipTests", "package"]],
        "tests": [["mvn", "-q", "test"]],
    },
    "bundler": {
        "setup": [["bundle", "install"]],
        "build": [],
        "tests": [["bundle", "exec", "rspec"]],
    },
}

_IMAGE_BY_MANAGER: dict[str, str] = {
    "uv": "ghcr.io/astral-sh/uv:python3.12-bookworm-slim",
    "poetry": "python:3.12-slim",
    "pip": "python:3.12-slim",
    "npm": "node:22-slim",
    "pnpm": "node:22-slim",
    "yarn": "node:22-slim",
    "go": "golang:1.24-slim",
    "cargo": "rust:1.85-slim",
    "maven": "maven:3.9-eclipse-temurin-21",
    "bundler": "ruby:3.3-slim",
}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_bounded(path: Path) -> str | None:
    """Read a regular file of bounded size without following symlinks."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > _MAX_TEXT_BYTES:
        return None
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read(_MAX_TEXT_BYTES + 1)
        if len(payload) > _MAX_TEXT_BYTES:
            return None
        return payload.decode("utf-8", "replace")
    except OSError:
        return None
    finally:
        os.close(descriptor)


def _hash_file_bounded(path: Path, cap: int = _MAX_LOCKFILE_BYTES) -> str | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > cap:
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _is_security_path(relative: str) -> bool:
    posix = PurePosixPath(relative.replace("\\", "/"))
    parts = {part.lower() for part in posix.parts}
    name = posix.name.lower()
    return (
        name == ".env"
        or name.startswith(".env.")
        or name in _SECURITY_FILE_NAMES
        or name.endswith((".key", ".pem", ".p12", ".pfx"))
        or bool(parts & _SECURITY_PATH_PARTS)
    )


@dataclass(frozen=True, slots=True)
class LanguageDetection:
    """Detected programming languages by non-config file count."""

    languages: tuple[str, ...]
    primary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PackageManagerDetection:
    """Detected package managers and their manifests/lockfiles."""

    managers: tuple[str, ...]
    manifests: tuple[str, ...]
    lockfiles: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ToolchainDetection:
    """Detected test/build tooling and deterministic commands."""

    test_tools: tuple[str, ...]
    test_patterns: tuple[str, ...]
    build_tools: tuple[str, ...]
    setup_commands: tuple[tuple[str, ...], ...]
    build_commands: tuple[tuple[str, ...], ...]
    test_commands: tuple[tuple[str, ...], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_tools": list(self.test_tools),
            "test_patterns": list(self.test_patterns),
            "build_tools": list(self.build_tools),
            "setup_commands": [list(cmd) for cmd in self.setup_commands],
            "build_commands": [list(cmd) for cmd in self.build_commands],
            "test_commands": [list(cmd) for cmd in self.test_commands],
        }


@dataclass(frozen=True, slots=True)
class MonorepoDetection:
    """Workspace layout when the repository is a monorepo."""

    kind: str
    workspaces: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RepositoryInspection:
    """Full deterministic inspection snapshot of one repository."""

    root: str
    languages: LanguageDetection
    package_managers: PackageManagerDetection
    toolchain: ToolchainDetection
    monorepo: MonorepoDetection
    ci_workflows: tuple[str, ...]
    codeowners: tuple[str, ...]
    agent_configs: tuple[str, ...]
    dockerfiles: tuple[str, ...]
    makefiles: tuple[str, ...]
    security_paths: tuple[str, ...]
    lockfile_digests: dict[str, str]
    has_git: bool
    git_head: str | None
    git_dirty_files: int = 0
    schema_version: int = 1

    @property
    def primary_manager(self) -> str | None:
        return self.package_managers.managers[0] if self.package_managers.managers else None

    def digest(self) -> str:
        payload = self.to_dict()
        payload.pop("git_head", None)
        payload.pop("git_dirty_files", None)
        return _canonical_digest(payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "root": self.root,
            "languages": self.languages.to_dict(),
            "package_managers": self.package_managers.to_dict(),
            "toolchain": self.toolchain.to_dict(),
            "monorepo": self.monorepo.to_dict(),
            "ci_workflows": list(self.ci_workflows),
            "codeowners": list(self.codeowners),
            "agent_configs": list(self.agent_configs),
            "dockerfiles": list(self.dockerfiles),
            "makefiles": list(self.makefiles),
            "security_paths": list(self.security_paths),
            "lockfile_digests": dict(sorted(self.lockfile_digests.items())),
            "has_git": self.has_git,
            "git_head": self.git_head,
            "git_dirty_files": self.git_dirty_files,
        }


class RepositoryInspector:
    """Walk a repository once and return a deterministic inspection snapshot."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)

    def inspect(self) -> RepositoryInspection:
        file_paths: list[Path] = []
        for directory, directory_names, file_names in os.walk(self.root, followlinks=False):
            directory_names[:] = sorted(
                name for name in directory_names if name not in _SCAN_IGNORED_NAMES
            )
            for name in sorted(file_names):
                if name in _SCAN_IGNORED_NAMES:
                    continue
                file_paths.append(Path(directory) / name)

        language_counts: dict[str, int] = {}
        manager_hits: list[str] = []
        manifest_hits: list[str] = []
        lockfile_hits: list[str] = []
        test_tools: list[str] = []
        test_patterns: list[str] = []
        build_tools: list[str] = []
        ci_workflows: list[str] = []
        codeowners: list[str] = []
        agent_configs: list[str] = []
        dockerfiles: list[str] = []
        makefiles: list[str] = []
        security_paths: list[str] = []
        lockfile_digests: dict[str, str] = {}
        workspaces: set[str] = set()
        monorepo_kind = "none"

        for path in file_paths:
            try:
                relative = path.relative_to(self.root).as_posix()
            except ValueError:
                continue
            name = path.name
            lowered = relative.lower()

            if name.endswith((".py", ".pyi")):
                language_counts["python"] = language_counts.get("python", 0) + 1
            elif name.endswith((".js", ".mjs", ".cjs", ".jsx")):
                language_counts["javascript"] = language_counts.get("javascript", 0) + 1
            elif name.endswith((".ts", ".mts", ".cts", ".tsx")):
                language_counts["typescript"] = language_counts.get("typescript", 0) + 1
            elif name.endswith((".go",)):
                language_counts["go"] = language_counts.get("go", 0) + 1
            elif name.endswith((".rs",)):
                language_counts["rust"] = language_counts.get("rust", 0) + 1
            elif name.endswith((".java",)):
                language_counts["java"] = language_counts.get("java", 0) + 1
            elif name.endswith((".rb",)):
                language_counts["ruby"] = language_counts.get("ruby", 0) + 1
            elif name.endswith((".php",)):
                language_counts["php"] = language_counts.get("php", 0) + 1
            elif name.endswith((".c", ".h")) and name not in {"config.h"}:
                language_counts["c"] = language_counts.get("c", 0) + 1
            elif name.endswith((".cpp", ".hpp", ".cc")):
                language_counts["cpp"] = language_counts.get("cpp", 0) + 1
            elif name.endswith((".cs",)):
                language_counts["csharp"] = language_counts.get("csharp", 0) + 1
            elif name.endswith((".swift",)):
                language_counts["swift"] = language_counts.get("swift", 0) + 1
            elif name.endswith((".kt", ".kts")):
                language_counts["kotlin"] = language_counts.get("kotlin", 0) + 1
            elif name.endswith((".ex", ".exs")):
                language_counts["elixir"] = language_counts.get("elixir", 0) + 1

            if name == "uv.lock":
                manifest_hits.append(relative)
                if "uv" not in manager_hits:
                    manager_hits.append("uv")
            elif name == "poetry.lock":
                manifest_hits.append(relative)
                if "poetry" not in manager_hits:
                    manager_hits.append("poetry")
            elif name == "requirements.txt":
                manifest_hits.append(relative)
                if "pip" not in manager_hits:
                    manager_hits.append("pip")
            elif name in _PYTHON_CONFIG_NAMES:
                manifest_hits.append(relative)
                if name in {"setup.py", "setup.cfg"}:
                    if "pip" not in manager_hits:
                        manager_hits.append("pip")
                elif name == "pyproject.toml":
                    has_uv = (path.parent / "uv.lock").is_file()
                    has_poetry = (path.parent / "poetry.lock").is_file()
                    if not has_uv and not has_poetry and "pip" not in manager_hits:
                        manager_hits.append("pip")
                if name in {"pytest.ini", "tox.ini", "conftest.py"} and "pytest" not in test_tools:
                    test_tools.append("pytest")
                if name == "pyproject.toml":
                    text = _read_bounded(path)
                    if text and "[tool.pytest" in text and "pytest" not in test_tools:
                        test_tools.append("pytest")
            if name == "package.json":
                manifest_hits.append(relative)
                text = _read_bounded(path) or ""
                manager = "npm"
                if (path.parent / "pnpm-lock.yaml").exists() or "pnpm" in text:
                    manager = "pnpm"
                elif (path.parent / "yarn.lock").exists():
                    manager = "yarn"
                elif (path.parent / "bun.lockb").exists():
                    manager = "bun"
                if manager not in manager_hits:
                    manager_hits.append(manager)
                scripts = _package_scripts(text)
                if "test" in scripts:
                    test_command = scripts["test"]
                    lowered_test = test_command.lower()
                    if "jest" in lowered_test and "jest" not in test_tools:
                        test_tools.append("jest")
                    elif "vitest" in lowered_test and "vitest" not in test_tools:
                        test_tools.append("vitest")
                    elif "mocha" in lowered_test and "mocha" not in test_tools:
                        test_tools.append("mocha")
                if (
                    "build" in scripts
                    and "npm" not in build_tools
                    and manager
                    in {
                        "npm",
                        "pnpm",
                        "yarn",
                    }
                ):
                    build_tools.append(manager)
            if name in {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"}:
                lockfile_hits.append(relative)
            if name in _GO_CONFIG_NAMES:
                manifest_hits.append(relative)
                if name in {"go.mod", "go.sum"} and "go" not in manager_hits:
                    manager_hits.append("go")
                if name == "go.work":
                    workspaces.add(relative)
                    monorepo_kind = "go-workspace" if monorepo_kind == "none" else monorepo_kind
            if name in _RUST_CONFIG_NAMES:
                manifest_hits.append(relative)
                if name == "Cargo.toml":
                    if "cargo" not in manager_hits:
                        manager_hits.append("cargo")
                    text = _read_bounded(path) or ""
                    if "[workspace]" in text:
                        workspaces.add(relative)
                        monorepo_kind = (
                            "cargo-workspace" if monorepo_kind == "none" else monorepo_kind
                        )
            if name in _JAVA_CONFIG_NAMES:
                manifest_hits.append(relative)
                if "maven" not in manager_hits and name == "pom.xml":
                    manager_hits.append("maven")
                if "gradle" not in manager_hits and name.startswith("build.gradle"):
                    manager_hits.append("gradle")
            if name in _RUBY_CONFIG_NAMES:
                manifest_hits.append(relative)
                if "bundler" not in manager_hits and name == "Gemfile":
                    manager_hits.append("bundler")
            if name in _PHP_CONFIG_NAMES:
                manifest_hits.append(relative)
                if "composer" not in manager_hits and name == "composer.json":
                    manager_hits.append("composer")
            if name in _ELIXIR_CONFIG_NAMES:
                manifest_hits.append(relative)
                if "mix" not in manager_hits and name == "mix.exs":
                    manager_hits.append("mix")

            if name == "Makefile":
                makefiles.append(relative)
                if "make" not in build_tools:
                    build_tools.append("make")
            if name == "Dockerfile" or (
                name.startswith("Dockerfile.") and name != "Dockerfile.dockerignore"
            ):
                dockerfiles.append(relative)
                if "docker" not in build_tools:
                    build_tools.append("docker")
            if name == "CMakeLists.txt" and "cmake" not in build_tools:
                build_tools.append("cmake")
            if name in {"nx.json", "lerna.json"}:
                workspaces.add(relative)
                monorepo_kind = "nx" if name == "nx.json" else monorepo_kind
                if "nx" not in build_tools:
                    build_tools.append("nx")
            if name == "pnpm-workspace.yaml":
                workspaces.add(relative)
                monorepo_kind = "pnpm-workspace" if monorepo_kind == "none" else monorepo_kind
            if name in {"WORKSPACE", "WORKSPACE.bazel", "BUILD", "BUILD.bazel", "MODULE.bazel"}:
                workspaces.add(relative)
                monorepo_kind = "bazel" if monorepo_kind == "none" else monorepo_kind
                if "bazel" not in build_tools:
                    build_tools.append("bazel")

            if relative.startswith(".github/workflows/") and name.endswith((".yml", ".yaml")):
                ci_workflows.append(relative)
            if name == "CODEOWNERS" and (
                relative == ".github/CODEOWNERS" or relative == "CODEOWNERS"
            ):
                codeowners.append(relative)
            if lowered in _AGENT_CONFIG_PATHS or relative.startswith(
                (".codex/", ".claude/", ".gemini/", ".copilot/", ".cursor/rules/")
            ):
                agent_configs.append(relative)
            if _is_security_path(relative):
                security_paths.append(relative)

            if name in {
                "uv.lock",
                "poetry.lock",
                "package-lock.json",
                "yarn.lock",
                "pnpm-lock.yaml",
                "go.sum",
                "Cargo.lock",
                "Gemfile.lock",
                "composer.lock",
                "mix.lock",
            }:
                digest = _hash_file_bounded(path)
                if digest is not None:
                    lockfile_digests[relative] = digest

        # Workspace package detection from package.json "workspaces" fields.
        for path in file_paths:
            if path.name != "package.json":
                continue
            text = _read_bounded(path) or ""
            if '"workspaces"' in text:
                workspaces.add(path.relative_to(self.root).as_posix())
                if monorepo_kind == "none":
                    monorepo_kind = "npm-workspaces"

        names_set = {path.name for path in file_paths}
        if "pytest" in test_tools or any(
            name.startswith("test_") or name.endswith("_test.py") for name in names_set
        ):
            if "pytest" not in test_tools:
                test_tools.append("pytest")
            test_patterns.append("tests/**")
        if any(
            name.endswith(
                (".test.js", ".test.ts", ".test.tsx", ".test.jsx", ".spec.js", ".spec.ts")
            )
            for name in names_set
        ):
            test_patterns.append("**/*.{test,spec}.{js,ts,jsx,tsx}")
        if any(name.endswith("_test.go") for name in names_set):
            if "go test" not in test_tools:
                test_tools.append("go test")
            test_patterns.append("**/*_test.go")

        language_order = sorted(language_counts.items(), key=lambda item: (-item[1], item[0]))
        languages = tuple(language for language, _ in language_order)
        primary = languages[0] if languages else "unknown"

        managers: list[str] = []
        for candidate in (
            "uv",
            "poetry",
            "pip",
            "pnpm",
            "yarn",
            "bun",
            "npm",
            "go",
            "cargo",
            "maven",
            "gradle",
            "bundler",
            "composer",
            "mix",
        ):
            if candidate in manager_hits:
                managers.append(candidate)
        if not managers:
            managers = _infer_manager_from_language(primary, file_paths)

        toolchain = self._build_toolchain(managers, test_tools, test_patterns, build_tools)
        return RepositoryInspection(
            root=str(self.root),
            languages=LanguageDetection(languages=languages, primary=primary),
            package_managers=PackageManagerDetection(
                managers=tuple(managers),
                manifests=tuple(sorted(set(manifest_hits))),
                lockfiles=tuple(sorted(set(lockfile_hits))),
            ),
            toolchain=toolchain,
            monorepo=MonorepoDetection(
                kind=monorepo_kind,
                workspaces=tuple(sorted(workspaces)),
            ),
            ci_workflows=tuple(sorted(ci_workflows)),
            codeowners=tuple(sorted(codeowners)),
            agent_configs=tuple(sorted(agent_configs)),
            dockerfiles=tuple(sorted(dockerfiles)),
            makefiles=tuple(sorted(makefiles)),
            security_paths=tuple(sorted(security_paths)),
            lockfile_digests=dict(sorted(lockfile_digests.items())),
            has_git=(self.root / ".git").exists(),
            git_head=self._git_head(),
            git_dirty_files=self._git_dirty_files(),
        )

    def _build_toolchain(
        self,
        managers: list[str],
        test_tools: list[str],
        test_patterns: list[str],
        build_tools: list[str],
    ) -> ToolchainDetection:
        setup: list[tuple[str, ...]] = []
        build: list[tuple[str, ...]] = []
        tests: list[tuple[str, ...]] = []
        for manager in managers:
            commands = _MANAGER_PROOF_COMMANDS.get(manager)
            if commands is None:
                continue
            setup.extend(tuple(command) for command in commands["setup"])
            build.extend(tuple(command) for command in commands["build"])
            tests.extend(tuple(command) for command in commands["tests"])
        if not tests and "pytest" in test_tools:
            tests.append(("python", "-m", "pytest", "-q"))
        return ToolchainDetection(
            test_tools=tuple(test_tools),
            test_patterns=tuple(test_patterns),
            build_tools=tuple(build_tools),
            setup_commands=tuple(setup),
            build_commands=tuple(build),
            test_commands=tuple(tests),
        )

    def _git_head(self) -> str | None:
        git_dir = self.root / ".git"
        if not git_dir.exists():
            return None
        try:
            result = subprocess.run(  # nosec B603
                ["git", "rev-parse", "HEAD"],
                cwd=self.root,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    def _git_dirty_files(self) -> int:
        git_dir = self.root / ".git"
        if not git_dir.exists():
            return 0
        try:
            result = subprocess.run(  # nosec B603
                ["git", "status", "--porcelain"],
                cwd=self.root,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return 0
        if result.returncode != 0:
            return 0
        return len([line for line in result.stdout.splitlines() if line.strip()])


def _package_scripts(text: str) -> dict[str, str]:
    try:
        import json as _json

        data = _json.loads(text)
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {str(key): str(value) for key, value in scripts.items() if isinstance(value, str)}


def _infer_manager_from_language(primary: str, file_paths: Iterable[Path]) -> list[str]:
    """Fallback manager inference when no explicit manifest is present."""
    paths = list(file_paths)
    if primary == "go" and any(path.name == "go.mod" for path in paths):
        return ["go"]
    if primary == "rust" and any(path.name == "Cargo.toml" for path in paths):
        return ["cargo"]
    if primary == "python" and any(path.name == "pyproject.toml" for path in paths):
        return ["pip"]
    if primary in {"javascript", "typescript"} and any(
        path.name == "package.json" for path in paths
    ):
        return ["npm"]
    if primary == "java" and any(path.name == "pom.xml" for path in paths):
        return ["maven"]
    if primary == "ruby" and any(path.name == "Gemfile" for path in paths):
        return ["bundler"]
    return []


def inspection_to_policy(inspection: RepositoryInspection) -> dict[str, Any]:
    """Derive a conservative, deterministic policy from an inspection snapshot.

    This is the single-source-of-truth compilation step: one repository
    inspection produces one policy, which every agent adapter then references
    instead of maintaining per-agent security rules.
    """
    primary = inspection.primary_manager
    allow_write: list[str] = []
    review: list[str] = []
    deny: list[str] = [
        ".env",
        ".env.*",
        ".git/**",
        ".ssh/**",
        ".agentdiff/**",
        "agentdiff.yaml",
        "**/*.key",
        "**/*.pem",
    ]
    for path in inspection.security_paths:
        deny.append(path)

    if "python" in inspection.languages.languages:
        allow_write.extend(["src/**", "tests/**", "**/*.py"])
    if "javascript" in inspection.languages.languages or (
        "typescript" in inspection.languages.languages
    ):
        allow_write.extend(["src/**", "tests/**", "**/*.{js,jsx,ts,tsx}"])
    if "go" in inspection.languages.languages:
        allow_write.extend(["**/*.go"])
    if "rust" in inspection.languages.languages:
        allow_write.extend(["src/**", "tests/**", "**/*.rs"])
    if "java" in inspection.languages.languages:
        allow_write.extend(["src/**", "**/*.java"])
    if "ruby" in inspection.languages.languages:
        allow_write.extend(["app/**", "lib/**", "spec/**", "**/*.rb"])

    for path in inspection.package_managers.manifests:
        review.append(path)
    for path in inspection.package_managers.lockfiles:
        review.append(path)
    for path in inspection.ci_workflows:
        review.append(path)
    review.extend(inspection.dockerfiles)
    review.extend(inspection.makefiles)
    review.extend(inspection.agent_configs)

    process_allow = [
        "python*",
        "pytest",
        "uv",
        "node",
        "npm",
        "npx",
        "pnpm",
        "yarn",
        "go",
        "cargo",
        "mvn",
        "gradle",
        "ruby",
        "bundle",
        "docker",
        "make",
        "cmake",
        "git",
    ]
    image = None
    if primary is not None:
        image = _IMAGE_BY_MANAGER.get(primary)

    proof = {
        "image": image,
        "network": False,
        "setup": [list(cmd) for cmd in inspection.toolchain.setup_commands],
        "build": [list(cmd) for cmd in inspection.toolchain.build_commands],
        "tests": [list(cmd) for cmd in inspection.toolchain.test_commands],
    }

    return {
        "version": 2,
        "filesystem": {
            "allow_write": sorted(set(allow_write)),
            "review": sorted(set(review)),
            "deny": sorted(set(deny)),
            "default": "review",
        },
        "process": {
            "allow": sorted(set(process_allow)),
            "review": [],
            "deny": [],
            "default": "review",
        },
        "network": {"mode": "observe"},
        "limits": {
            "files_changed": 100,
            "files_deleted": 10,
            "processes_spawned": 32,
            "duration_seconds": 900,
        },
        "rollback": {"enabled": True, "max_backup_file_mb": 25},
        "scoring": {"weights": {}},
        "proof": proof,
    }
