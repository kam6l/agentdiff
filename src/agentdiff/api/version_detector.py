"""SDK version detection from repository dependency manifests and lockfiles."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

_LIBRARY_TO_PROVIDER = {
    "openai": "openai",
    "stripe": "stripe",
}


@dataclass(frozen=True, slots=True)
class SDKVersionInfo:
    """Detected installed/required SDK version for an API provider."""

    provider: str
    library: str
    exact_version: str | None
    version_specifier: str | None
    source_file: str
    is_exact: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SDKVersionInfo:
        return cls(
            provider=str(data["provider"]),
            library=str(data["library"]),
            exact_version=data.get("exact_version"),
            version_specifier=data.get("version_specifier"),
            source_file=str(data.get("source_file", "")),
            is_exact=bool(data.get("is_exact", False)),
        )


def _clean_req_specifier(line: str) -> tuple[str, str | None, str | None]:
    """Parse requirement line (e.g. 'openai==0.28.1' or 'stripe>=7.0.0')."""
    cleaned = line.split("#", 1)[0].split(";", 1)[0].strip()
    if not cleaned:
        return "", None, None

    # Match library name and version constraint
    match = re.match(r"^([A-Za-z0-9_.\-]+)\s*([<>=~!^].*)?$", cleaned)
    if not match:
        return "", None, None

    lib = match.group(1).lower().replace("-", "_")
    spec = match.group(2).strip() if match.group(2) else None
    exact: str | None = None
    if spec and spec.startswith("=="):
        exact_candidate = spec.lstrip("=").strip()
        try:
            Version(exact_candidate)
            exact = exact_candidate
        except InvalidVersion:
            exact = None

    return lib, spec, exact


def _parse_uv_lock(path: Path) -> dict[str, SDKVersionInfo]:
    """Extract exact package versions from uv.lock."""
    results: dict[str, SDKVersionInfo] = {}
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return results

    current_pkg: str | None = None
    for line in content.splitlines():
        line = line.strip()
        if line == "[[package]]":
            current_pkg = None
            continue
        if line.startswith("name = "):
            name = line.split("=", 1)[1].strip().strip('"').strip("'").lower().replace("-", "_")
            if name in _LIBRARY_TO_PROVIDER:
                current_pkg = name
        elif line.startswith("version = ") and current_pkg:
            ver = line.split("=", 1)[1].strip().strip('"').strip("'")
            prov = _LIBRARY_TO_PROVIDER[current_pkg]
            results[prov] = SDKVersionInfo(
                provider=prov,
                library=current_pkg,
                exact_version=ver,
                version_specifier=f"=={ver}",
                source_file=path.name,
                is_exact=True,
            )
            current_pkg = None
    return results


def _parse_poetry_lock(path: Path) -> dict[str, SDKVersionInfo]:
    """Extract exact package versions from poetry.lock."""
    results: dict[str, SDKVersionInfo] = {}
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return results

    current_pkg: str | None = None
    for line in content.splitlines():
        line = line.strip()
        if line == "[[package]]":
            current_pkg = None
            continue
        if line.startswith("name = "):
            name = line.split("=", 1)[1].strip().strip('"').strip("'").lower().replace("-", "_")
            if name in _LIBRARY_TO_PROVIDER:
                current_pkg = name
        elif line.startswith("version = ") and current_pkg:
            ver = line.split("=", 1)[1].strip().strip('"').strip("'")
            prov = _LIBRARY_TO_PROVIDER[current_pkg]
            results[prov] = SDKVersionInfo(
                provider=prov,
                library=current_pkg,
                exact_version=ver,
                version_specifier=f"=={ver}",
                source_file=path.name,
                is_exact=True,
            )
            current_pkg = None
    return results


def _parse_pyproject_toml(path: Path) -> dict[str, SDKVersionInfo]:
    """Extract dependency version constraints from pyproject.toml."""
    results: dict[str, SDKVersionInfo] = {}
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return results

    for line in content.splitlines():
        line_clean = line.strip().strip('"').strip("'").strip(",")
        # Look for e.g. "openai>=1.0.0" or openai = "^1.0.0"
        if "=" in line_clean and not any(
            line_clean.startswith(p) for p in ("name", "version", "description")
        ):
            parts = line_clean.split("=", 1)
            candidate_lib = parts[0].strip().strip('"').strip("'").lower().replace("-", "_")
            if candidate_lib in _LIBRARY_TO_PROVIDER:
                raw_val = parts[1].strip().strip('"').strip("'").strip(",").strip()
                prov = _LIBRARY_TO_PROVIDER[candidate_lib]
                exact: str | None = None
                if raw_val.startswith("=="):
                    exact = raw_val[2:].strip()
                results[prov] = SDKVersionInfo(
                    provider=prov,
                    library=candidate_lib,
                    exact_version=exact,
                    version_specifier=raw_val,
                    source_file=path.name,
                    is_exact=exact is not None,
                )
                continue

        lib, spec, exact = _clean_req_specifier(line_clean)
        if lib in _LIBRARY_TO_PROVIDER:
            prov = _LIBRARY_TO_PROVIDER[lib]
            results[prov] = SDKVersionInfo(
                provider=prov,
                library=lib,
                exact_version=exact,
                version_specifier=spec,
                source_file=path.name,
                is_exact=exact is not None,
            )
    return results


def _parse_requirements_txt(path: Path) -> dict[str, SDKVersionInfo]:
    """Extract dependency versions from a requirements.txt file."""
    results: dict[str, SDKVersionInfo] = {}
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return results

    for line in content.splitlines():
        lib, spec, exact = _clean_req_specifier(line)
        if lib in _LIBRARY_TO_PROVIDER:
            prov = _LIBRARY_TO_PROVIDER[lib]
            results[prov] = SDKVersionInfo(
                provider=prov,
                library=lib,
                exact_version=exact,
                version_specifier=spec,
                source_file=path.name,
                is_exact=exact is not None,
            )
    return results


def detect_installed_sdk_versions(root: str | Path) -> dict[str, SDKVersionInfo]:
    """Scan root repository for dependency manifests and lockfiles in priority order."""
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        if root_path.is_file():
            root_path = root_path.parent
        else:
            return {}

    detected: dict[str, SDKVersionInfo] = {}

    # Priority 1: Exact Lockfiles
    uv_lock = root_path / "uv.lock"
    if uv_lock.is_file():
        for prov, info in _parse_uv_lock(uv_lock).items():
            if prov not in detected:
                detected[prov] = info

    poetry_lock = root_path / "poetry.lock"
    if poetry_lock.is_file():
        for prov, info in _parse_poetry_lock(poetry_lock).items():
            if prov not in detected:
                detected[prov] = info

    # Priority 2: pyproject.toml
    pyproject = root_path / "pyproject.toml"
    if pyproject.is_file():
        for prov, info in _parse_pyproject_toml(pyproject).items():
            if prov not in detected or not detected[prov].is_exact:
                detected[prov] = info

    # Priority 3: requirements*.txt files in root and requirements/ dir
    req_candidates: list[Path] = []
    for f in root_path.glob("requirements*.txt"):
        if f.is_file():
            req_candidates.append(f)
    for f in root_path.glob("*-requirements.txt"):
        if f.is_file():
            req_candidates.append(f)
    req_dir = root_path / "requirements"
    if req_dir.is_dir():
        for f in req_dir.glob("*.txt"):
            if f.is_file():
                req_candidates.append(f)

    for req_file in req_candidates:
        for prov, info in _parse_requirements_txt(req_file).items():
            if prov not in detected or not detected[prov].is_exact:
                detected[prov] = info

    return detected


def is_version_affected(installed: SDKVersionInfo | None, breaking_spec: str) -> bool:
    """Evaluate whether an installed/configured SDK version satisfies a breaking constraint."""
    if not breaking_spec or not breaking_spec.strip():
        return True

    if installed is None:
        # Version unknown -> fail closed (assume affected for safety)
        return True

    # 1. Exact version comparison
    if installed.exact_version:
        try:
            ver = Version(installed.exact_version)
            spec = SpecifierSet(breaking_spec)
            return ver in spec
        except (InvalidVersion, InvalidSpecifier):
            pass

    # 2. Specifier comparison
    if installed.version_specifier:
        clean_spec = installed.version_specifier.strip()
        # Handle poetry caret syntax, e.g. "^1.0.0" -> ">=1.0.0"
        if clean_spec.startswith("^"):
            clean_spec = f">={clean_spec[1:]}"
        elif clean_spec.startswith("~="):
            clean_spec = clean_spec

        try:
            inst_spec = SpecifierSet(clean_spec)
            break_spec = SpecifierSet(breaking_spec)
            # If breaking_spec is ">=1.0.0" and installed is "==0.28.1" or "<1.0.0", not affected
            # Test sample point on installed specifier
            if installed.exact_version:
                return Version(installed.exact_version) in break_spec

            # If installed constraint explicitly requires < 1.0.0 and breaking is >= 1.0.0
            if "<" in str(inst_spec) and ">=" in str(break_spec):
                # E.g. installed is "<1.0.0" and breaking is ">=1.0.0"
                return False
        except (InvalidSpecifier, InvalidVersion):
            pass

    # Default to affected if cannot prove safe
    return True
