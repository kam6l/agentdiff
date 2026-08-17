"""Workspace materializer correctness and trust-boundary tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
import hashlib
import os
import stat

import pytest

from agentdiff.runtime import MaterializationStrategy, WorkspaceMaterializer


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_tree(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "script.sh").write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    (root / "script.sh").chmod(0o755)
    (root / "empty.txt").write_text("", encoding="utf-8")
    (root / "src" / "nested").mkdir()
    (root / "src" / "nested" / "deep.txt").write_text("x" * 2_000_000, encoding="utf-8")


@pytest.mark.parametrize(
    "strategy",
    [
        MaterializationStrategy.AUTO,
        MaterializationStrategy.FAST_COPY,
        MaterializationStrategy.STREAM_COPY,
    ],
)
def test_materializer_preserves_content_size_and_mode(tmp_path: Path, strategy: object) -> None:
    src = tmp_path / "source"
    dst = tmp_path / "target"
    src.mkdir()
    make_tree(src)

    report = WorkspaceMaterializer(strategy=strategy).materialize(src, dst)

    assert report.files_materialized == 4
    assert (dst / "script.sh").read_text(encoding="utf-8") == "#!/bin/sh\necho hi\n"
    assert (dst / "empty.txt").read_text(encoding="utf-8") == ""
    assert len((dst / "src" / "nested" / "deep.txt").read_bytes()) == 2_000_000
    assert (dst / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    if os.name != "nt":
        assert stat.S_IMODE((dst / "script.sh").stat().st_mode) == 0o755
        assert stat.S_IMODE((dst / "src" / "app.py").stat().st_mode) == 0o644
    # No live-host or sealed-source mutation.
    assert sha256_bytes((src / "script.sh").read_bytes()) == sha256_bytes(
        (dst / "script.sh").read_bytes()
    )
    assert (src / "src" / "nested" / "deep.txt").stat().st_size == 2_000_000


def test_materializer_rejects_symlink(tmp_path: Path) -> None:
    src = tmp_path / "source"
    dst = tmp_path / "target"
    src.mkdir()
    (src / "app.py").write_text("x", encoding="utf-8")
    os.symlink(tmp_path / "outside.txt", src / "link.txt")

    with pytest.raises(RuntimeError, match="symlink"):
        WorkspaceMaterializer().materialize(src, dst)
    # The offending symlink is never materialized or followed. The copy is
    # not transactional across files (walk order is filesystem-dependent);
    # the caller discards the failed private workspace.
    assert not (dst / "link.txt").exists()


def test_materializer_rejects_hardlink(tmp_path: Path) -> None:
    src = tmp_path / "source"
    dst = tmp_path / "target"
    src.mkdir()
    first = src / "first.txt"
    first.write_text("shared", encoding="utf-8")
    os.link(first, src / "second.txt")

    with pytest.raises(RuntimeError, match="hardlink"):
        WorkspaceMaterializer().materialize(src, dst)


@pytest.mark.skipif(os.name == "nt", reason="named pipes are POSIX-only")
def test_materializer_rejects_special_file(tmp_path: Path) -> None:
    import os as _os

    src = tmp_path / "source"
    dst = tmp_path / "target"
    src.mkdir()
    _os.mkfifo(src / "pipe.fifo")

    with pytest.raises(RuntimeError, match="special file"):
        WorkspaceMaterializer().materialize(src, dst)


def test_materializer_rejects_target_symlink(tmp_path: Path) -> None:
    src = tmp_path / "source"
    src.mkdir()
    (src / "app.py").write_text("x", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    dst = tmp_path / "target"
    os.symlink(outside, dst)

    with pytest.raises(ValueError, match="real directory"):
        WorkspaceMaterializer().materialize(src, dst)
    assert not (outside / "app.py").exists()


def test_materializer_fast_copy_reports_actual_strategy(tmp_path: Path) -> None:
    src = tmp_path / "source"
    dst = tmp_path / "target"
    src.mkdir()
    (src / "app.py").write_text("x" * 100, encoding="utf-8")

    report = WorkspaceMaterializer(strategy=MaterializationStrategy.STREAM_COPY).materialize(
        src, dst
    )
    assert report.strategy_used in {"stream_copy", "clone", "fast_copy"}
    assert report.files_materialized == 1
    assert report.bytes_materialized == 100


def test_materializer_ignores_git_and_agentdiff_dirs(tmp_path: Path) -> None:
    src = tmp_path / "source"
    dst = tmp_path / "target"
    src.mkdir()
    (src / "app.py").write_text("x", encoding="utf-8")
    (src / ".git").mkdir()
    (src / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (src / ".agentdiff").mkdir()
    (src / ".agentdiff" / "secret").write_text("hidden", encoding="utf-8")

    report = WorkspaceMaterializer().materialize(src, dst)
    assert report.files_materialized == 1
    assert not (dst / ".git").exists()
    assert not (dst / ".agentdiff").exists()
