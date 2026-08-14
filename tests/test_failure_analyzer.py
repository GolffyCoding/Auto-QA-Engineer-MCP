"""Unit tests for qa_mcp.failure_analysis.analyzer - weighted pattern
classification, evidence persistence, and run comparison. These drive the
fix_loop's diagnosis step, so a misclassification here cascades into a
wrong patch proposal.
"""
import pytest

from qa_mcp.failure_analysis.analyzer import FailureAnalyzer, FailureEvidence


@pytest.fixture
def analyzer(tmp_path):
    return FailureAnalyzer(state_path=str(tmp_path / "state.json"))


def test_specific_pattern_beats_generic_overlapping_pattern(analyzer):
    # "timeout" alone is a low-weight pattern shared by api/database/network,
    # but "foreign key constraint" is a specific high-weight database pattern.
    # The specific one must win even though both match the same text.
    evidence = FailureEvidence(
        failure_id="f1", test_name="t", expected="ok",
        actual="request failed", server_log="foreign key constraint violated, timeout after retry",
    )
    diagnosis = analyzer.inspect(evidence)
    assert diagnosis.category == "database"


def test_unknown_category_when_no_pattern_matches(analyzer):
    evidence = FailureEvidence(
        failure_id="f2", test_name="t", expected="foo", actual="something unexpected happened",
    )
    diagnosis = analyzer.inspect(evidence)
    assert diagnosis.category == "unknown"


def test_confidence_increases_with_more_evidence(analyzer):
    bare = FailureEvidence(failure_id="f3", test_name="t", expected="e", actual="HTTP 500 error")
    rich = FailureEvidence(
        failure_id="f4", test_name="t", expected="e", actual="HTTP 500 error",
        screenshot="s.png", server_log="log", database_state={"users": []}, console_log="c",
    )
    bare_diag = analyzer.inspect(bare)
    rich_diag = analyzer.inspect(rich)
    assert rich_diag.confidence > bare_diag.confidence


def test_get_evidence_returns_none_before_inspect(analyzer):
    assert analyzer.get_evidence("never-inspected") is None


def test_get_evidence_returns_stored_evidence_after_inspect(analyzer):
    evidence = FailureEvidence(failure_id="f5", test_name="t", expected="e", actual="HTTP 404")
    analyzer.inspect(evidence)
    stored = analyzer.get_evidence("f5")
    assert stored.actual == "HTTP 404"


def test_evidence_persists_across_new_analyzer_instance(tmp_path):
    path = str(tmp_path / "state.json")
    first = FailureAnalyzer(state_path=path)
    first.inspect(FailureEvidence(failure_id="f6", test_name="t", expected="e", actual="HTTP 401"))

    second = FailureAnalyzer(state_path=path)
    stored = second.get_evidence("f6")
    assert stored is not None
    assert stored.actual == "HTTP 401"


def test_compare_runs_finds_new_fixed_and_still_failing():
    run1 = {"run_id": "r1", "results": [
        {"test_id": "a", "status": "passed"},
        {"test_id": "b", "status": "failed"},
        {"test_id": "c", "status": "failed"},
    ]}
    run2 = {"run_id": "r2", "results": [
        {"test_id": "a", "status": "failed"},
        {"test_id": "b", "status": "passed"},
        {"test_id": "c", "status": "failed"},
    ]}

    analyzer = FailureAnalyzer()
    result = analyzer.compare_runs(run1, run2)

    assert result["new_failures"] == ["a"]
    assert result["fixed_failures"] == ["b"]
    assert result["still_failing"] == ["c"]
    assert result["regressions"] == result["new_failures"]


def test_find_regression_only_flags_previously_passing_tests():
    baseline = [{"test_id": "a", "status": "passed"}, {"test_id": "b", "status": "failed"}]
    current = [{"test_id": "a", "status": "failed"}, {"test_id": "b", "status": "failed"}]

    analyzer = FailureAnalyzer()
    regressions = analyzer.find_regression(current, baseline)

    assert [r["test_id"] for r in regressions] == ["a"]
