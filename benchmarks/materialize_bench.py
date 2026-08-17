#!/usr/bin/env python3
"""Measured workspace-materializer throughput benchmark (not a unit test).

Run with: uv run python3 benchmarks/materialize_bench.py --output materialize-bench.json

Measures streaming copy throughput and per-file cost across file counts so
materializer performance claims are measured, not assumed.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

from agentdiff.runtime import MaterializationStrategy, WorkspaceMaterializer


@dataclass(frozen=True, slots=True)
class BenchCase:
    files: int
    bytes_per_file: int
    strategy: str
    duration_seconds: float
    files_per_second: float
    mib_per_second: float


def build_tree(root: Path, files: int, bytes_per_file: int) -> None:
    payload = bytes((index % 251 for index in range(bytes_per_file)))
    for index in range(files):
        subdir = root / f"d{index % 50}"
        subdir.mkdir(exist_ok=True)
        (subdir / f"f{index}.bin").write_bytes(payload)


def run_case(root: Path, files: int, bytes_per_file: int, strategy: object) -> BenchCase:
    src = root / f"src-{files}-{bytes_per_file}"
    dst = root / f"dst-{files}-{bytes_per_file}-{strategy.value}"
    src.mkdir(exist_ok=True)
    build_tree(src, files, bytes_per_file)
    started = perf_counter()
    report = WorkspaceMaterializer(strategy=strategy).materialize(src, dst)
    duration = perf_counter() - started
    total_bytes = files * bytes_per_file
    return BenchCase(
        files=files,
        bytes_per_file=bytes_per_file,
        strategy=report.strategy_used,
        duration_seconds=duration,
        files_per_second=files / duration if duration else 0.0,
        mib_per_second=(total_bytes / (1024 * 1024)) / duration if duration else 0.0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="materialize-bench.json")
    args = parser.parse_args()

    cases: list[BenchCase] = []
    with tempfile.TemporaryDirectory(prefix="agentdiff-bench-") as temporary:
        root = Path(temporary)
        for files, size in [(1_000, 4_096), (10_000, 4_096)]:
            for strategy in (
                MaterializationStrategy.STREAM_COPY,
                MaterializationStrategy.FAST_COPY,
                MaterializationStrategy.AUTO,
            ):
                cases.append(run_case(root, files, size, strategy))
                print(
                    f"{files:>7} files x {size} B  {strategy.value:12} -> "
                    f"{cases[-1].files_per_second:9.0f} files/s "
                    f"{cases[-1].mib_per_second:8.1f} MiB/s"
                )
    payload = {
        "benchmark": "agentdiff-materializer",
        "schema_version": 1,
        "cases": [asdict(case) for case in cases],
    }
    Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Results written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
