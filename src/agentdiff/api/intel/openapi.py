"""OpenAPI diff analyzer: detect breaking changes between two OpenAPI specs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentdiff.api.models import ChangeSeverity, ChangeType


@dataclass(frozen=True, slots=True)
class OpenAPIBreakingChange:
    """One breaking change detected between two OpenAPI documents."""

    path: str  # operation path like /v1/chat/completions
    method: str  # get/post/put/delete...
    operation_id: str
    change_type: ChangeType
    severity: ChangeSeverity
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "method": self.method,
            "operation_id": self.operation_id,
            "change_type": self.change_type.value,
            "severity": self.severity.value,
            "detail": self.detail,
        }


def _load_spec(source: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(source, dict):
        return source
    path = Path(source)
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    # Minimal YAML support without forcing a dependency: fall back to JSON,
    # since OpenAPI JSON is the common machine-readable interchange.
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


class OpenAPIDiffAnalyzer:
    """Compare two OpenAPI documents and report breaking changes."""

    def __init__(self, provider: str) -> None:
        self.provider = provider

    def diff(
        self,
        before: str | Path | dict[str, Any],
        after: str | Path | dict[str, Any],
    ) -> list[OpenAPIBreakingChange]:
        """Return breaking changes between two OpenAPI documents."""
        old_spec = _load_spec(before)
        new_spec = _load_spec(after)
        changes: list[OpenAPIBreakingChange] = []

        old_paths = self._operations(old_spec)
        new_paths = self._operations(new_spec)

        old_by_key = {(p, m): op for (p, m), op in old_paths.items()}
        new_by_key = {(p, m): op for (p, m), op in new_paths.items()}

        # Removed operations
        for key, op in old_by_key.items():
            if key not in new_by_key:
                path, method = key
                changes.append(
                    OpenAPIBreakingChange(
                        path=path,
                        method=method,
                        operation_id=op.get("operationId", ""),
                        change_type=ChangeType.REMOVAL,
                        severity=ChangeSeverity.CRITICAL,
                        detail="operation removed",
                    )
                )

        # Changed operations
        for key, old_op in old_by_key.items():
            new_op = new_by_key.get(key)
            if new_op is None:
                continue
            changes.extend(self._diff_operation(key, old_op, new_op))

        return changes

    def _operations(self, spec: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
        result: dict[tuple[str, str], dict[str, Any]] = {}
        paths = spec.get("paths", {})
        if not isinstance(paths, dict):
            return result
        for path, item in paths.items():
            if not isinstance(item, dict):
                continue
            for method in ("get", "post", "put", "delete", "patch"):
                op = item.get(method)
                if isinstance(op, dict):
                    result[(path, method)] = op
        return result

    def _diff_operation(
        self,
        key: tuple[str, str],
        old_op: dict[str, Any],
        new_op: dict[str, Any],
    ) -> list[OpenAPIBreakingChange]:
        path, method = key
        changes: list[OpenAPIBreakingChange] = []
        old_op_id = old_op.get("operationId", "")

        # Required parameters removed
        old_required = {p.get("name") for p in old_op.get("parameters", []) if p.get("required")}
        new_params = {p.get("name") for p in new_op.get("parameters", [])}
        removed_required = old_required - new_params
        for name in sorted(removed_required):
            changes.append(
                OpenAPIBreakingChange(
                    path=path,
                    method=method,
                    operation_id=old_op_id,
                    change_type=ChangeType.PARAMETER_REMOVAL,
                    severity=ChangeSeverity.HIGH,
                    detail=f"required parameter removed: {name}",
                )
            )

        # Request body removed
        old_body = "requestBody" in old_op
        new_body = "requestBody" in new_op
        if old_body and not new_body:
            changes.append(
                OpenAPIBreakingChange(
                    path=path,
                    method=method,
                    operation_id=old_op_id,
                    change_type=ChangeType.SIGNATURE_CHANGE,
                    severity=ChangeSeverity.HIGH,
                    detail="request body removed",
                )
            )

        return changes
