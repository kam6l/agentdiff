"""AST-based Python scanner for detecting external API usages with provenance tracking."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Iterable, Sequence

from agentdiff.api.models import APIUsage
from agentdiff.api.providers import APIProvider, get_all_providers
from agentdiff.pathing import normalize_relative_path

_DEFAULT_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        ".env",
        "__pycache__",
        ".agentdiff",
        ".tox",
        ".nox",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        "dist",
        "build",
        "eggs",
        ".eggs",
    }
)


def _get_call_name(node: ast.AST) -> str | None:
    """Recursively reconstruct dotted attribute/call expression name."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _get_call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _get_call_name(node.func)
    return None


def _extract_arg_literal(node: ast.AST) -> str:
    """Extract literal string/number representation from an AST node if constant."""
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        name = _get_call_name(node)
        return name if name is not None else ""
    return ast.unparse(node) if hasattr(ast, "unparse") else ""


class _APIUsageVisitor(ast.NodeVisitor):
    """AST visitor extracting proven API calls and imports."""

    def __init__(
        self,
        filepath: str,
        source_lines: list[str],
        providers: Sequence[APIProvider],
    ) -> None:
        self.filepath = filepath
        self.source_lines = source_lines
        self.providers = providers
        self.usages: list[APIUsage] = []

        # Name bindings: local alias -> canonical qualified name
        self.imported_names: dict[str, str] = {}
        # Client instances: local var or attr (e.g. "client", "self.client") -> provider name
        self.client_vars: dict[str, str] = {}
        # Scope stack (function and class names)
        self.scope_stack: list[str] = []

    def _get_snippet(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()
        return ""

    def _get_enclosing_scope(self) -> str:
        return ".".join(self.scope_stack) if self.scope_stack else "global"

    def _find_provider_for_symbol(self, symbol: str) -> APIProvider | None:
        root = symbol.split(".")[0]
        for p in self.providers:
            if root in p.import_names:
                return p
        return None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local_name = alias.asname or alias.name
            self.imported_names[local_name] = alias.name

            provider = self._find_provider_for_symbol(alias.name)
            if provider is not None:
                self.usages.append(
                    APIUsage(
                        provider=provider.name,
                        library=provider.library,
                        symbol=alias.name,
                        call_type="import",
                        filepath=self.filepath,
                        line_number=node.lineno,
                        column=node.col_offset,
                        code_snippet=self._get_snippet(node.lineno),
                        enclosing_scope=self._get_enclosing_scope(),
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        provider = self._find_provider_for_symbol(module)
        for alias in node.names:
            local_name = alias.asname or alias.name
            full_imported = f"{module}.{alias.name}" if module else alias.name
            self.imported_names[local_name] = full_imported

            p = provider or self._find_provider_for_symbol(full_imported)
            if p is not None:
                self.usages.append(
                    APIUsage(
                        provider=p.name,
                        library=p.library,
                        symbol=full_imported,
                        call_type="import",
                        filepath=self.filepath,
                        line_number=node.lineno,
                        column=node.col_offset,
                        code_snippet=self._get_snippet(node.lineno),
                        enclosing_scope=self._get_enclosing_scope(),
                    )
                )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Check client instantiation: e.g. client = OpenAI(...) or self.client = OpenAI(...)
        if isinstance(node.value, ast.Call):
            call_name = _get_call_name(node.value.func)
            if call_name:
                resolved = self._resolve_symbol(call_name)
                if resolved in {
                    "openai.OpenAI",
                    "openai.AsyncOpenAI",
                    "openai.AzureOpenAI",
                    "openai.AsyncAzureOpenAI",
                }:
                    for target in node.targets:
                        target_name = _get_call_name(target)
                        if target_name:
                            self.client_vars[target_name] = "openai"
                elif resolved in {
                    "stripe.StripeClient",
                    "stripe.Client",
                }:
                    for target in node.targets:
                        target_name = _get_call_name(target)
                        if target_name:
                            self.client_vars[target_name] = "stripe"

        # Check configuration attribute assignments, e.g. openai.api_key = "..."
        for target in node.targets:
            target_name = _get_call_name(target)
            if target_name:
                resolved = self._resolve_symbol(target_name)
                provider = self._find_provider_for_symbol(resolved)
                if provider is not None:
                    val_str = _extract_arg_literal(node.value)
                    kwargs = {"value": val_str} if val_str else {}
                    self.usages.append(
                        APIUsage(
                            provider=provider.name,
                            library=provider.library,
                            symbol=resolved,
                            call_type="attribute",
                            filepath=self.filepath,
                            line_number=node.lineno,
                            column=node.col_offset,
                            keyword_arguments=kwargs,
                            code_snippet=self._get_snippet(node.lineno),
                            enclosing_scope=self._get_enclosing_scope(),
                        )
                    )

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        raw_name = _get_call_name(node.func)
        if raw_name:
            resolved_symbol, provider_name = self._resolve_call_symbol(raw_name)
            if provider_name is not None and resolved_symbol is not None:
                provider = next((p for p in self.providers if p.name == provider_name), None)
                if provider is not None:
                    args: list[str] = [_extract_arg_literal(arg) for arg in node.args]
                    kwargs: dict[str, str] = {
                        kw.arg: _extract_arg_literal(kw.value) for kw in node.keywords if kw.arg
                    }

                    self.usages.append(
                        APIUsage(
                            provider=provider.name,
                            library=provider.library,
                            symbol=resolved_symbol,
                            call_type="call",
                            filepath=self.filepath,
                            line_number=node.lineno,
                            column=node.col_offset,
                            arguments=tuple(args),
                            keyword_arguments=kwargs,
                            code_snippet=self._get_snippet(node.lineno),
                            enclosing_scope=self._get_enclosing_scope(),
                        )
                    )

        self.generic_visit(node)

    def _resolve_symbol(self, name: str) -> str:
        parts = name.split(".")
        root = parts[0]
        if root in self.imported_names:
            base = self.imported_names[root]
            return ".".join([base, *parts[1:]]) if len(parts) > 1 else base
        return name

    def _resolve_call_symbol(self, raw_name: str) -> tuple[str | None, str | None]:
        parts = raw_name.split(".")

        # 1. Check if raw_name or any prefix is a proven client instance
        for i in range(len(parts), 0, -1):
            prefix = ".".join(parts[:i])
            if prefix in self.client_vars:
                provider_name = self.client_vars[prefix]
                subpath = ".".join(parts[i:])
                symbol = f"client.{subpath}" if subpath else "client"
                return symbol, provider_name

        # 2. Check if variable/module comes from imported names
        resolved = self._resolve_symbol(raw_name)
        provider = self._find_provider_for_symbol(resolved)
        if provider is not None:
            return resolved, provider.name

        # No ungrounded guessing - if not proven by import or client binding, return None
        return None, None


class APIScanner:
    """Scanner for discovering external API usages across Python source files."""

    def __init__(
        self,
        providers: Sequence[APIProvider] | None = None,
        ignored_dirs: Iterable[str] = _DEFAULT_IGNORED_DIRS,
    ) -> None:
        self.providers: list[APIProvider] = (
            list(providers) if providers is not None else get_all_providers()
        )
        self.ignored_dirs = frozenset(ignored_dirs)

    def scan_code(
        self,
        code: str,
        filepath: str = "<memory>",
    ) -> list[APIUsage]:
        """Scan a Python code string and extract API usages."""
        try:
            tree = ast.parse(code, filename=filepath)
        except (SyntaxError, ValueError, TypeError):
            return []

        source_lines = code.splitlines()
        visitor = _APIUsageVisitor(
            filepath=filepath,
            source_lines=source_lines,
            providers=self.providers,
        )
        visitor.visit(tree)
        return visitor.usages

    def scan_file(self, path: str | Path) -> list[APIUsage]:
        """Scan a single Python file."""
        p = Path(path).resolve()
        if not p.is_file():
            return []

        try:
            code = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        return self.scan_code(code, filepath=str(p))

    def scan_repository(
        self,
        root: str | Path,
    ) -> list[APIUsage]:
        """Recursively scan a repository directory for all Python files and extract API usages."""
        root_path = Path(root).expanduser().resolve()
        if not root_path.is_dir():
            raise FileNotFoundError(f"directory not found: {root}")

        all_usages: list[APIUsage] = []

        for dirpath, dirnames, filenames in os.walk(root_path, followlinks=False):
            dirnames[:] = [
                d for d in dirnames if d not in self.ignored_dirs and not d.startswith(".")
            ]

            for fname in sorted(filenames):
                if not fname.endswith(".py"):
                    continue

                full_path = Path(dirpath) / fname
                try:
                    rel_path = normalize_relative_path(str(full_path.relative_to(root_path)))
                except ValueError:
                    rel_path = fname

                usages = self.scan_code(
                    full_path.read_text(encoding="utf-8", errors="replace"),
                    filepath=rel_path,
                )
                all_usages.extend(usages)

        return all_usages

    scan = scan_repository
    scan_directory = scan_repository
