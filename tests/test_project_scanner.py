"""Unit tests for qa_mcp.project_intelligence.scanner - found via real
end-to-end testing (scanning this project's own repo through the CLI)
rather than from reading the code first: scanning "." produced a blank
project name, and a Python-only project was misclassified as language
"Unknown" because vendor/VCS directories weren't excluded from the walk.
"""
import pytest

from qa_mcp.project_intelligence.scanner import ProjectScanner


def test_scan_current_directory_does_not_produce_blank_name(tmp_path, monkeypatch):
    """Path('.').name is '' - scanning the project root with '.' (the most
    common invocation) must not produce a blank project name.
    """
    monkeypatch.chdir(tmp_path)
    scanner = ProjectScanner(".")
    assert scanner.profile.name == tmp_path.name


def test_scan_excludes_git_internals_from_language_detection(tmp_path):
    """A project with far more .git-internal files (no extension) than
    source files must still be classified by its actual source files, not
    by VCS/vendor noise.
    """
    (tmp_path / ".git" / "objects" / "aa").mkdir(parents=True)
    for i in range(50):
        (tmp_path / ".git" / "objects" / "aa" / f"blob{i}").write_text("binary-ish")

    (tmp_path / "main.py").write_text("print('hi')\n")
    (tmp_path / "utils.py").write_text("def f(): pass\n")

    scanner = ProjectScanner(str(tmp_path))
    scanner.detect_stack()
    assert scanner.profile.language == "Python"


def test_scan_excludes_node_modules_from_route_and_component_search(tmp_path):
    (tmp_path / "node_modules" / "some-lib").mkdir(parents=True)
    (tmp_path / "node_modules" / "some-lib" / "component.tsx").write_text("<form></form>")

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "checkout-component.tsx").write_text("export const X = () => null;")

    scanner = ProjectScanner(str(tmp_path))
    scanner.scan()
    assert all("node_modules" not in c for c in scanner.profile.components)


def test_scan_does_not_misdetect_flask_from_a_file_merely_named_app_py(tmp_path):
    """Found live: this repo's own sample-apps/*/app.py files (plain
    stdlib http.server, nothing to do with Flask) made every project.scan
    of this project misreport framework: Flask, because "app.py" was used
    as a Flask indicator - an extremely common filename with no real
    signal value on its own.
    """
    (tmp_path / "app.py").write_text("import http.server\n")
    (tmp_path / "requirements.txt").write_text("httpx>=0.24\n")

    scanner = ProjectScanner(str(tmp_path))
    scanner.detect_stack()
    assert scanner.profile.framework == "Unknown"


def test_scan_still_detects_flask_from_real_dependency_declaration(tmp_path):
    (tmp_path / "app.py").write_text("import http.server\n")
    (tmp_path / "requirements.txt").write_text("Flask>=3.0\n")

    scanner = ProjectScanner(str(tmp_path))
    scanner.detect_stack()
    assert scanner.profile.framework == "Flask"
