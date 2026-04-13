"""
tests/test_analyzer.py — ProjectAnalyzer 단위 테스트
"""

import pytest
from pathlib import Path
from core.analyzer import ProjectAnalyzer


@pytest.fixture
def sample_project(tmp_path):
    """간단한 가상 프로젝트 픽스처."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main(): pass")
    (tmp_path / "src" / "utils.py").write_text("def helper(): pass")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_main(): pass")
    (tmp_path / "requirements.txt").write_text("fastapi==0.111.0")
    (tmp_path / "README.md").write_text("# My Project")
    # node_modules는 무시되어야 함
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "some.js").write_text("// ignored")
    return tmp_path


def test_analyze_finds_python_files(sample_project):
    analyzer = ProjectAnalyzer()
    structure = analyzer.analyze(sample_project)
    extensions = [f.extension for f in structure.code_files]
    assert extensions.count(".py") == 3


def test_analyze_finds_config_files(sample_project):
    analyzer = ProjectAnalyzer()
    structure = analyzer.analyze(sample_project)
    config_names = [f.path.name for f in structure.config_files]
    assert "requirements.txt" in config_names
    assert "README.md" in config_names


def test_analyze_ignores_node_modules(sample_project):
    analyzer = ProjectAnalyzer()
    structure = analyzer.analyze(sample_project)
    all_paths = [f.relative_path for f in structure.all_files]
    assert not any("node_modules" in p for p in all_paths)


def test_tree_is_string(sample_project):
    analyzer = ProjectAnalyzer()
    structure = analyzer.analyze(sample_project)
    assert isinstance(structure.tree, str)
    assert len(structure.tree) > 0
