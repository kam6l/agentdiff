"""Repository dependency/impact graph for impact-aware proof planning.

The graph is built deterministically from static import analysis (Python,
JavaScript/TypeScript, Go, Rust). It maps changed files to affected modules,
affected tests, and build targets so proof can be targeted instead of always
running the entire repository suite.
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from agentdiff.pathing import normalize_relative_path

_MAX_SOURCE_BYTES = 512 * 1024
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
        "target",
        ".idea",
        ".vscode",
    }
)

_PY_IMPORT_RE = re.compile(r"^\s*(?:import\s+([\w.]+)|from\s+([\w.]+)\s+import)", re.MULTILINE)
_TS_IMPORT_RE = re.compile(
    r"""(?:import\s*[^'"]*?from\s*['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\)|import\s*\(\s*['"]([^'"]+)['"]\s*\))""",
    re.MULTILINE,
)
_GO_IMPORT_RE = re.compile(r'^\s*import\s+(?:[a-zA-Z_]\w*\s+)?"([^"]+)"', re.MULTILINE)
_GO_IMPORT_BLOCK_RE = re.compile(r'^\s*"([^"]+)"$', re.MULTILINE)
_RUST_USE_RE = re.compile(r"^\s*use\s+(?:crate|self|super)::([\w:]+)", re.MULTILINE)
_RUST_MOD_RE = re.compile(r"^\s*(?:pub\s+)?mod\s+(\w+)\s*;", re.MULTILINE)

_TEST_FILE_SUFFIXES = (
    "_test.go",
    ".test.js",
    ".test.jsx",
    ".test.ts",
    ".test.tsx",
    ".spec.js",
    ".spec.jsx",
    ".spec.ts",
    ".spec.tsx",
)


def _read_bounded(path: Path) -> str | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > _MAX_SOURCE_BYTES:
        return None
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read(_MAX_SOURCE_BYTES + 1)
        if len(payload) > _MAX_SOURCE_BYTES:
            return None
        return payload.decode("utf-8", "replace")
    except OSError:
        return None
    finally:
        os.close(descriptor)


@dataclass(frozen=True, slots=True)
class GraphNode:
    """One node in the impact graph: file, module, test, or build target."""

    kind: str
    id: str
    path: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "id": self.id, "path": self.path}


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """One directed dependency edge."""

    source: str
    target: str
    kind: str  # "owns" | "imports" | "tests"

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "kind": self.kind}


@dataclass(frozen=True, slots=True)
class ImpactSet:
    """Affected modules, tests, and build targets for a set of changed files."""

    modules: tuple[str, ...]
    tests: tuple[str, ...]
    build_targets: tuple[str, ...]
    direct: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "modules": list(self.modules),
            "tests": list(self.tests),
            "build_targets": list(self.build_targets),
            "direct": list(self.direct),
        }


class RepoImpactGraph:
    """Deterministic import/ownership graph for one repository."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        python_packages: Iterable[str] = (),
        go_module_path: str | None = None,
        workspace_packages: Mapping[str, str] | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)
        self.python_packages = tuple(python_packages)
        self.go_module_path = go_module_path
        self.workspace_packages = dict(workspace_packages or {})
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self.file_to_modules: dict[str, tuple[str, ...]] = {}
        self.module_to_files: dict[str, tuple[str, ...]] = {}
        self.module_to_tests: dict[str, tuple[str, ...]] = {}
        self._build()

    @classmethod
    def from_inspection(cls, root: str | os.PathLike[str]) -> "RepoImpactGraph":
        """Build a graph, using an inspection snapshot to resolve packages."""

        python_packages: list[str] = []
        go_module: str | None = None
        workspaces: dict[str, str] = {}
        for directory, directory_names, file_names in os.walk(Path(root), followlinks=False):
            directory_names.sort()
            file_names.sort()
            dir_path = Path(directory)
            if any(part in _SCAN_IGNORED_NAMES for part in dir_path.relative_to(Path(root)).parts):
                continue
            relative = dir_path.relative_to(Path(root)).as_posix()
            if (dir_path / "__init__.py").is_file() and not dir_path.parent.name.startswith("."):
                python_packages.append(relative)
            for name in file_names:
                if name == "go.mod" and go_module is None:
                    text = _read_bounded(dir_path / name)
                    if text:
                        match = re.search(r"^\s*module\s+(\S+)", text, re.MULTILINE)
                        if match:
                            go_module = match.group(1)
                if name == "package.json":
                    text = _read_bounded(dir_path / name)
                    if text:
                        try:
                            data = json.loads(text)
                        except (ValueError, TypeError):
                            continue
                        if isinstance(data, dict) and isinstance(data.get("name"), str):
                            workspaces[data["name"]] = relative
        return cls(
            root,
            python_packages=sorted(set(python_packages)),
            go_module_path=go_module,
            workspace_packages=dict(sorted(workspaces.items())),
        )

    def _build(self) -> None:
        source_files: list[Path] = []
        for directory, directory_names, file_names in os.walk(self.root, followlinks=False):
            directory_names[:] = sorted(
                name for name in directory_names if name not in _SCAN_IGNORED_NAMES
            )
            for name in sorted(file_names):
                if name in _SCAN_IGNORED_NAMES:
                    continue
                source_files.append(Path(directory) / name)

        # 1. Register file nodes and module ownership.
        for path in source_files:
            try:
                relative = path.relative_to(self.root).as_posix()
            except ValueError:
                continue
            self._add_node("file", relative, path=relative)
            module_id = self._module_for(relative)
            if module_id is not None:
                self.file_to_modules[relative] = (module_id,)
                self._add_edge(module_id, relative, "owns")

        # 2. Resolve imports.
        for path in source_files:
            try:
                relative = path.relative_to(self.root).as_posix()
            except ValueError:
                continue
            module_id = self._module_for(relative)
            if module_id is None:
                continue
            text = _read_bounded(path)
            if text is None:
                continue
            if relative.endswith(".py"):
                targets = self._resolve_python_imports(relative, text)
            elif relative.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")):
                targets = self._resolve_ts_imports(relative, text)
            elif relative.endswith(".go"):
                targets = self._resolve_go_imports(relative, text)
            elif relative.endswith(".rs"):
                targets = self._resolve_rust_imports(relative, text)
            else:
                targets = []
            for target in targets:
                target_module = self._module_for(target) or target
                self._add_edge(module_id, target_module, "imports")

        # 3. Tests that exercise modules.
        for path in source_files:
            try:
                relative = path.relative_to(self.root).as_posix()
            except ValueError:
                continue
            if not self._is_test_file(relative):
                continue
            test_module = self._module_for(relative)
            if test_module is None:
                test_module = relative
            text = _read_bounded(path)
            if text is None:
                continue
            covered: set[str] = set()
            if relative.endswith(".py"):
                covered.update(self._resolve_python_imports(relative, text))
            elif relative.endswith((".js", ".jsx", ".ts", ".tsx")):
                covered.update(self._resolve_ts_imports(relative, text))
            elif relative.endswith(".go"):
                covered.update(self._resolve_go_imports(relative, text))
            elif relative.endswith(".rs"):
                covered.update(self._resolve_rust_imports(relative, text))
            for target in covered:
                module = self._module_for(target) or target
                self._add_edge(test_module, module, "tests")
                self.module_to_tests.setdefault(module, ())
                if test_module not in self.module_to_tests[module]:
                    self.module_to_tests[module] = (*self.module_to_tests[module], test_module)

        self._finalize_module_maps()

    def _finalize_module_maps(self) -> None:
        for relative, modules in self.file_to_modules.items():
            for module in modules:
                self.module_to_files.setdefault(module, ())
                if relative not in self.module_to_files[module]:
                    self.module_to_files[module] = (*self.module_to_files[module], relative)

    # ---- node/edge helpers -------------------------------------------------

    def _add_node(self, kind: str, node_id: str, *, path: str = "") -> None:
        self.nodes.setdefault(node_id, GraphNode(kind=kind, id=node_id, path=path))

    def _add_edge(self, source: str, target: str, kind: str) -> None:
        if source == target:
            return
        self.edges.append(GraphEdge(source=source, target=target, kind=kind))

    def _module_for(self, relative: str) -> str | None:
        posix = PurePosixPath(relative)
        if posix.name.endswith(".py"):
            stem = posix.with_suffix("").as_posix()
            parts = stem.split("/")
            return ".".join(parts)
        if posix.name.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")):
            return posix.with_suffix("").as_posix()
        if posix.name.endswith(".go"):
            return posix.with_suffix("").as_posix()
        if posix.name.endswith(".rs"):
            return posix.with_suffix("").as_posix()
        return None

    @staticmethod
    def _is_test_file(relative: str) -> bool:
        posix = PurePosixPath(relative)
        name = posix.name
        return bool(
            name.endswith(_TEST_FILE_SUFFIXES)
            or (name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py")))
            or (name.endswith(".rs") and ("tests" in posix.parts or name.endswith("_test.rs")))
        )

    # ---- per-language import resolution ------------------------------------

    def _resolve_python_imports(self, relative: str, text: str) -> list[str]:
        resolved: set[str] = set()
        package_parts: list[str] = []
        current = PurePosixPath(relative).parent
        while current.as_posix() != ".":
            package_parts.append(current.name)
            current = current.parent
        package_parts.reverse()
        for full_name, from_name in _PY_IMPORT_RE.findall(text):
            name = full_name or from_name
            if not name:
                continue
            if name.startswith("."):
                # Relative import: count leading dots.
                dots = len(name) - len(name.lstrip("."))
                base = (
                    package_parts[: len(package_parts) - (dots - 1)] if dots > 1 else package_parts
                )
                rest = name.lstrip(".").split(".")
                candidate = ".".join([*base, *rest])
            else:
                candidate = name
            for target in self._resolve_python_candidate(candidate):
                resolved.add(target)
            # Try stripping one level at a time for partial matches.
            parts = candidate.split(".")
            for index in range(len(parts) - 1, 0, -1):
                for target in self._resolve_python_candidate(".".join(parts[:index])):
                    resolved.add(target)
        return sorted(resolved)

    def _resolve_python_candidate(self, dotted: str) -> list[str]:
        hits: list[str] = []
        for package in self.python_packages:
            prefix = f"{package}." if package else ""
            if dotted == package or dotted.startswith(prefix):
                rest = dotted[len(package) + 1 :] if dotted != package else ""
                if not rest:
                    hits.append(package)
                    continue
                module_path = f"{package}/{rest.replace('.', '/')}"
                for candidate in (f"{module_path}.py", f"{module_path}/__init__.py"):
                    if (self.root / candidate).is_file():
                        hits.append(candidate)
        # Top-level module file at repository root.
        if "." not in dotted:
            for candidate in (f"{dotted}.py", f"{dotted}/__init__.py"):
                if (self.root / candidate).is_file():
                    hits.append(candidate)
        return sorted(set(hits))

    def _resolve_ts_imports(self, relative: str, text: str) -> list[str]:
        resolved: set[str] = set()
        current_dir = PurePosixPath(relative).parent.as_posix()
        for match in _TS_IMPORT_RE.findall(text):
            specifier = next((part for part in match if part), None)
            if not specifier:
                continue
            if specifier.startswith("."):
                base = PurePosixPath(current_dir) if current_dir != "." else PurePosixPath(".")
                target = (base / specifier).as_posix()
                for candidate in self._expand_module_suffixes(target):
                    resolved.add(candidate)
            else:
                package_name = specifier.split("/", 1)[0]
                package_dir = self.workspace_packages.get(package_name)
                if package_dir is None:
                    continue
                sub = specifier.split("/", 1)[1] if "/" in specifier else "index"
                base = PurePosixPath(package_dir)
                target = (base / sub).as_posix()
                for candidate in self._expand_module_suffixes(target):
                    resolved.add(candidate)
        return sorted(resolved)

    @staticmethod
    def _expand_module_suffixes(target: str) -> list[str]:
        candidates: list[str] = []
        for suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
            candidates.append(f"{target}{suffix}")
        if target.endswith("/index"):
            candidates.append(target)
        else:
            candidates.append(f"{target}/index.ts")
            candidates.append(f"{target}/index.js")
        return candidates

    def _resolve_go_imports(self, relative: str, text: str) -> list[str]:
        resolved: set[str] = set()
        if self.go_module_path is None:
            return []
        imports: list[str] = []
        for match in _GO_IMPORT_RE.findall(text):
            imports.append(match)
        in_block = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ("):
                in_block = True
                continue
            if in_block:
                if stripped == ")":
                    in_block = False
                    continue
                block_match = _GO_IMPORT_BLOCK_RE.match(stripped)
                if block_match:
                    imports.append(block_match.group(1))
        for import_path in imports:
            if import_path.startswith(f"{self.go_module_path}/"):
                rest = import_path[len(self.go_module_path) + 1 :]
                resolved.add(f"{rest}.go")
        return sorted(resolved)

    def _resolve_rust_imports(self, relative: str, text: str) -> list[str]:
        resolved: set[str] = set()
        current_dir = PurePosixPath(relative).parent.as_posix()
        for match in _RUST_USE_RE.findall(text):
            first = match.split("::")[0]
            parts = match.split("::")[1:] if first == "crate" else [first, *match.split("::")[1:]]
            if not parts:
                continue
            for depth in range(1, len(parts) + 1):
                path_parts = parts[:depth]
                candidate_rs = "/".join([current_dir, *path_parts]) + ".rs"
                candidate_dir = "/".join([current_dir, *path_parts]) + "/mod.rs"
                if (self.root / candidate_rs).is_file():
                    resolved.add(candidate_rs)
                if (self.root / candidate_dir).is_file():
                    resolved.add(candidate_dir)
        # `mod x;` declarations are local module edges.
        for match in _RUST_MOD_RE.findall(text):
            candidate_rs = f"{current_dir}/{match}.rs" if current_dir != "." else f"{match}.rs"
            candidate_dir = (
                f"{current_dir}/{match}/mod.rs" if current_dir != "." else f"{match}/mod.rs"
            )
            if (self.root / candidate_rs).is_file():
                resolved.add(candidate_rs)
            if (self.root / candidate_dir).is_file():
                resolved.add(candidate_dir)
        return sorted(resolved)

    # ---- queries ------------------------------------------------------------

    def affected(self, changed_paths: Iterable[str]) -> ImpactSet:
        """Return modules, tests, and build targets affected by changed files.

        Affected modules are the modules owning each changed file plus every
        module that imports them (transitively, one hop). Affected tests are the
        tests that cover any affected module. Build targets are derived from the
        changed paths' module namespace.
        """
        direct_modules: set[str] = set()
        for raw in changed_paths:
            normalized = normalize_relative_path(raw)
            modules = self.file_to_modules.get(normalized, ())
            direct_modules.update(modules)
        affected_modules: set[str] = set(direct_modules)
        for module in list(direct_modules):
            for edge in self.edges:
                if edge.kind == "imports" and edge.target == module:
                    affected_modules.add(edge.source)
                    # One more hop for test coverage breadth.
                    for edge2 in self.edges:
                        if edge2.kind == "imports" and edge2.target == edge.source:
                            affected_modules.add(edge2.source)
        affected_tests: set[str] = set()
        for module in affected_modules:
            affected_tests.update(self.module_to_tests.get(module, ()))
        # Tests that directly import changed files are always included.
        for raw in changed_paths:
            normalized = normalize_relative_path(raw)
            for test_module, covered in self.module_to_tests.items():
                for module in self.file_to_modules.get(normalized, ()):
                    if module in covered:
                        affected_tests.add(test_module)
        build_targets = self._build_targets_for(sorted(affected_modules))
        return ImpactSet(
            modules=tuple(sorted(affected_modules)),
            tests=tuple(sorted(affected_tests)),
            build_targets=tuple(sorted(build_targets)),
            direct=tuple(sorted(direct_modules)),
        )

    def _build_targets_for(self, modules: Iterable[str]) -> set[str]:
        targets: set[str] = set()
        for module in modules:
            parts = module.split(".")
            if len(parts) >= 2 and (self.root / parts[0]).is_dir():
                targets.add(f"python:{parts[0]}")
            else:
                targets.add("python:root")
            if (self.root / "go.mod").is_file():
                targets.add("go:./...")
            if (self.root / "Cargo.toml").is_file():
                targets.add("cargo:workspace")
            if (self.root / "package.json").is_file():
                targets.add("npm:root")
        return targets

    def serialize(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "root": str(self.root),
            "nodes": [node.to_dict() for node in sorted(self.nodes.values(), key=lambda n: n.id)],
            "edges": [
                edge.to_dict()
                for edge in sorted(self.edges, key=lambda e: (e.source, e.target, e.kind))
            ],
            "python_packages": sorted(self.python_packages),
            "go_module_path": self.go_module_path,
            "workspace_packages": dict(sorted(self.workspace_packages.items())),
        }
