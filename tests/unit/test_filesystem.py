from __future__ import annotations

from pathlib import Path

from sgm.adapters.filesystem import FileSystemAdapter


def test_scan_skips_hidden_paths_and_symlinks(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".venv" / "bin").mkdir(parents=True)
    (repo_root / "__pycache__").mkdir()
    (repo_root / "src").mkdir()
    (repo_root / "src" / "module.py").write_text("print('ok')\n", encoding="utf-8")
    (repo_root / "__pycache__" / "module.cpython-312.pyc").write_text("x", encoding="utf-8")
    (repo_root / ".venv" / "bin" / "python3.12").symlink_to("/bin/sh")

    adapter = FileSystemAdapter(repo_root=repo_root)

    nodes = adapter.scan(".")

    paths = {node.path for node in nodes}
    assert "." in paths
    assert "src" in paths
    assert "src/module.py" in paths
    assert ".venv" not in paths
    assert ".venv/bin/python3.12" not in paths
    assert "__pycache__" not in paths
    assert "__pycache__/module.cpython-312.pyc" not in paths
