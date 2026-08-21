"""Provider plugin system: load migrations from provider/community packages.

Layout of an installed provider plugin (local directory or git checkout)::

    providers/<name>/
        metadata.yaml          provider name, library, version
        manifests/             *.yaml APIChangeManifest files
        transforms/            python modules registering AST transforms
        tests/                 optional plugin tests
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from agentdiff.api.manifest import APIChangeManifest, register_builtin_manifest
from agentdiff.api.transforms.base import MigrationTransform, register_transform

_PLUGIN_ROOT_NAME = "providers"


class PluginTrust(str, Enum):
    """Execution trust assigned by the local operator."""

    DATA_ONLY = "DATA_ONLY"
    UNTRUSTED_CODE = "UNTRUSTED_CODE"
    TRUSTED_CODE = "TRUSTED_CODE"


@dataclass(frozen=True, slots=True)
class ProviderPlugin:
    """A loaded provider plugin."""

    name: str
    library: str
    root: Path
    manifests: tuple[APIChangeManifest, ...]
    transforms: tuple[MigrationTransform, ...]
    metadata: dict[str, Any]
    trust: PluginTrust = PluginTrust.DATA_ONLY
    source_digest: str = ""
    executable_code_present: bool = False
    code_loaded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "library": self.library,
            "root": str(self.root),
            "manifest_count": len(self.manifests),
            "transform_count": len(self.transforms),
            "metadata": self.metadata,
            "trust": self.trust.value,
            "source_digest": self.source_digest,
            "executable_code_present": self.executable_code_present,
            "code_loaded": self.code_loaded,
        }


def discover_plugins(plugins_dir: str | Path = _PLUGIN_ROOT_NAME) -> list[Path]:
    """Find provider plugin directories under the plugins root."""
    root = Path(plugins_dir)
    if not root.is_dir():
        return []
    return sorted(d for d in root.iterdir() if d.is_dir() and (d / "metadata.yaml").is_file())


def load_plugin(plugin_dir: str | Path, *, allow_code: bool = False) -> ProviderPlugin:
    """Load plugin data; execute code only after two explicit trust gates.

    A plugin must declare ``TRUSTED_CODE`` *and* the caller must pass
    ``allow_code=True``. Installed or discovered Python is never executed by
    default.
    """
    root = Path(plugin_dir).expanduser().resolve(strict=True)
    metadata_path = root / "metadata.yaml"
    if not metadata_path.is_file():
        raise ValueError(f"plugin missing metadata.yaml: {root}")

    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or not metadata.get("name"):
        raise ValueError(f"plugin metadata must define 'name': {root}")

    name = str(metadata["name"])
    library = str(metadata.get("library", name))
    try:
        trust = PluginTrust(str(metadata.get("trust", PluginTrust.DATA_ONLY.value)).upper())
    except ValueError as error:
        raise ValueError(f"plugin {name} has invalid trust level") from error

    # Load manifests
    manifests: list[APIChangeManifest] = []
    manifests_dir = root / "manifests"
    if manifests_dir.is_dir():
        for manifest_file in sorted(manifests_dir.glob("*.y*ml")) + sorted(
            manifests_dir.glob("*.json")
        ):
            if manifest_file.suffix in {".yaml", ".yml"}:
                manifest = APIChangeManifest.from_yaml(manifest_file)
            else:
                manifest = APIChangeManifest.from_json(manifest_file)
            valid, errors = manifest.validate()
            if not valid:
                raise ValueError(f"plugin {name} manifest {manifest_file.name} invalid: {errors}")
            manifest_key = f"{manifest.provider}:{manifest.change_id}"
            if not manifest_key.startswith(f"{name}:"):
                # Namespace non-matching manifests under the plugin name.
                manifest = _replaced_change_id(manifest, f"{name}:{manifest.change_id}")
            manifests.append(manifest)
            register_builtin_manifest(manifest)

    # Load transforms from python modules in transforms/
    transforms: list[MigrationTransform] = []
    transforms_dir = root / "transforms"
    code_files = (
        tuple(path for path in sorted(transforms_dir.glob("*.py")) if not path.name.startswith("_"))
        if transforms_dir.is_dir()
        else ()
    )
    code_loaded = bool(code_files) and trust is PluginTrust.TRUSTED_CODE and allow_code
    if code_loaded:
        for module_file in code_files:
            # Load by file path with a unique module name to avoid collisions
            # with real provider packages (e.g. `stripe`).
            module_name = f"_agentdiff_plugin_{name}_{module_file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, module_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            except Exception:  # noqa: BLE001 - plugin isolation boundary
                # A broken plugin transform must not take down the whole load.
                sys.modules.pop(module_name, None)
                continue
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, MigrationTransform)
                    and attr is not MigrationTransform
                    and getattr(attr, "transform_id", None)
                ):
                    try:
                        transform = attr()
                    except Exception:  # noqa: BLE001 - plugin isolation boundary
                        continue
                    transforms.append(transform)
                    register_transform(transform)

    return ProviderPlugin(
        name=name,
        library=library,
        root=root,
        manifests=tuple(manifests),
        transforms=tuple(transforms),
        metadata=metadata,
        trust=trust,
        source_digest=_source_digest(root),
        executable_code_present=bool(code_files),
        code_loaded=code_loaded,
    )


def install_plugin(
    name: str, source: str | Path, plugins_dir: str | Path = _PLUGIN_ROOT_NAME
) -> Path:
    """Install a provider plugin by copying a local source directory."""
    if not name or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for character in name.lower()
    ):
        raise ValueError("plugin name may contain only letters, digits, hyphens, and underscores")
    src = Path(source).expanduser().resolve(strict=True)
    if not (src / "metadata.yaml").is_file():
        raise ValueError(f"source is not a provider plugin (missing metadata.yaml): {src}")
    _source_digest(src)
    root = Path(plugins_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest = root / name
    if dest.exists():
        raise FileExistsError(f"plugin already installed: {dest}")
    import shutil

    shutil.copytree(src, dest)
    return dest


def list_plugins(plugins_dir: str | Path = _PLUGIN_ROOT_NAME) -> list[ProviderPlugin]:
    """Load provider data without executing third-party code."""
    return [load_plugin(d) for d in discover_plugins(plugins_dir)]


def _source_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        if path.is_symlink():
            raise ValueError(f"plugin contains a symlink: {path.relative_to(root)}")
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _replaced_change_id(manifest: APIChangeManifest, new_id: str) -> APIChangeManifest:
    from dataclasses import replace

    return replace(manifest, change_id=new_id)
