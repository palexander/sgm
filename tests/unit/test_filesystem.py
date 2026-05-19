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


def test_scan_prunes_nested_git_repos_and_node_modules(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src").mkdir()
    (repo_root / "src" / "module.py").write_text("print('ok')\n", encoding="utf-8")
    (repo_root / "vendor" / "nested-repo" / ".git").mkdir(parents=True)
    (repo_root / "vendor" / "nested-repo" / "inner.py").write_text(
        "print('nested')\n",
        encoding="utf-8",
    )
    (repo_root / "packages" / "app" / "node_modules" / "dep").mkdir(parents=True)
    (repo_root / "packages" / "app" / "node_modules" / "dep" / "index.js").write_text(
        "module.exports = {}\n",
        encoding="utf-8",
    )
    (repo_root / "packages" / "app" / "index.js").write_text(
        "module.exports = {}\n",
        encoding="utf-8",
    )

    adapter = FileSystemAdapter(repo_root=repo_root)

    nodes = adapter.scan(".")

    paths = {node.path for node in nodes}
    assert "." in paths
    assert "src" in paths
    assert "src/module.py" in paths
    assert "packages" in paths
    assert "packages/app" in paths
    assert "packages/app/index.js" in paths
    assert "packages/app/node_modules" not in paths
    assert "packages/app/node_modules/dep" not in paths
    assert "packages/app/node_modules/dep/index.js" not in paths
    assert "vendor" in paths
    assert "vendor/nested-repo" not in paths
    assert "vendor/nested-repo/.git" not in paths
    assert "vendor/nested-repo/inner.py" not in paths


def test_inventory_nodes_uses_explicit_file_list(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "specs").mkdir()
    (repo_root / "src" / "services").mkdir(parents=True)
    (repo_root / "specs" / "example.sgm.yaml").write_text("id: spec-001\n", encoding="utf-8")
    (repo_root / "src" / "services" / "handler.ts").write_text(
        "export const handler = () => {}\n",
        encoding="utf-8",
    )
    (repo_root / ".gitignore").write_text(".sgm/work/\n", encoding="utf-8")

    adapter = FileSystemAdapter(repo_root=repo_root)

    nodes = adapter.inventory_nodes(
        (
            ".gitignore",
            "specs/example.sgm.yaml",
            "src/services/handler.ts",
        )
    )

    paths = {node.path for node in nodes}
    assert "." in paths
    assert ".gitignore" in paths
    assert "specs" in paths
    assert "specs/example.sgm.yaml" in paths
    assert "src" in paths
    assert "src/services" in paths
    assert "src/services/handler.ts" in paths


def test_inventory_nodes_skips_sgm_state_and_nested_noise(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".gitignore").write_text(".sgm/work/\n", encoding="utf-8")
    (repo_root / ".sgm" / "persisted" / "proposals").mkdir(parents=True)
    (repo_root / ".sgm" / "persisted" / "proposals" / "prop.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (repo_root / "vendor" / "nested-repo" / ".git").mkdir(parents=True)
    (repo_root / "vendor" / "nested-repo" / "inner.ts").write_text(
        "export {};\n",
        encoding="utf-8",
    )
    (repo_root / "packages" / "app" / "node_modules" / "dep").mkdir(parents=True)
    (repo_root / "packages" / "app" / "node_modules" / "dep" / "index.js").write_text(
        "module.exports = {}\n",
        encoding="utf-8",
    )
    (repo_root / "src").mkdir()
    (repo_root / "src" / "index.ts").write_text("export {};\n", encoding="utf-8")

    adapter = FileSystemAdapter(repo_root=repo_root)

    nodes = adapter.inventory_nodes(
        (
            ".gitignore",
            ".sgm/persisted/proposals/prop.json",
            "vendor/nested-repo/inner.ts",
            "packages/app/node_modules/dep/index.js",
            "src/index.ts",
        )
    )

    paths = {node.path for node in nodes}
    assert "." in paths
    assert ".gitignore" in paths
    assert "src" in paths
    assert "src/index.ts" in paths
    assert ".sgm/persisted/proposals/prop.json" not in paths
    assert "vendor/nested-repo/inner.ts" not in paths
    assert "packages/app/node_modules/dep/index.js" not in paths


def test_list_spec_files_discovers_specs_and_docs_specs(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "specs").mkdir()
    (repo_root / "docs" / "specs" / "nested").mkdir(parents=True)
    (repo_root / "specs" / "top-level.sgm.yaml").write_text(
        "id: spec-top\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "specs" / "epic-compatible-ui-auth.sgm.yaml").write_text(
        "id: spec-docs\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "specs" / "nested" / "extra.sgm.yml").write_text(
        "id: spec-nested\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "specs" / "notes.yaml").write_text(
        "id: not-a-spec\n",
        encoding="utf-8",
    )

    adapter = FileSystemAdapter(repo_root=repo_root)

    assert adapter.list_spec_files() == (
        "specs/top-level.sgm.yaml",
        "docs/specs/epic-compatible-ui-auth.sgm.yaml",
        "docs/specs/nested/extra.sgm.yml",
    )
