"""Unit tests for qa_mcp.test_design.generator - the deterministic test-case
generation engine (BVA, Equivalence Partitioning, OWASP, state-machine
coverage). This is the core selling point of the project, so its output
must be exhaustive and correct, not just "runs without crashing".
"""
import pytest

from qa_mcp.test_design.generator import TestDesigner
from qa_mcp.test_design.generator import test_generate as generate_tool
from qa_mcp.test_design.generator import test_analyze_coverage as analyze_coverage_tool


def test_field_based_generates_boundary_cases_at_and_over_max_length():
    designer = TestDesigner("checkout")
    suite = designer.generate_field_based_tests([
        {"name": "coupon_code", "type": "text", "required": False, "max_length": 20},
    ])

    titles = [c.title for c in suite.cases]
    assert any("at max length (20 chars)" in t for t in titles)
    assert any("exceeds max length (21 chars)" in t for t in titles)


def test_field_based_required_field_gets_negative_case():
    designer = TestDesigner("checkout")
    suite = designer.generate_field_based_tests([
        {"name": "amount", "type": "number", "required": True},
    ])

    negative = suite.by_category("Negative")
    assert any("missing required field 'amount'" in c.title for c in negative)


def test_field_based_optional_field_has_no_missing_required_case():
    designer = TestDesigner("checkout")
    suite = designer.generate_field_based_tests([
        {"name": "coupon_code", "type": "text", "required": False},
    ])

    negative = suite.by_category("Negative")
    assert not any("missing required field" in c.title for c in negative)


def test_security_probes_only_apply_to_injectable_field_types():
    designer = TestDesigner("checkout")
    suite = designer.generate_field_based_tests([
        {"name": "notes", "type": "text", "required": False},
        {"name": "status", "type": "select", "required": False},
    ])

    security = suite.by_category("Security")
    assert all("notes" in c.title for c in security)
    assert not any("status" in c.title for c in security)


def test_state_cycle_covers_full_matrix_positive_and_negative():
    designer = TestDesigner("order-status")
    suite = designer.generate_flow_based_tests(
        "order-status",
        states={
            "initial": "pending",
            "transitions": [
                {"from": "pending", "to": "paid", "action": "complete_payment"},
                {"from": "paid", "to": "shipped", "action": "ship_order"},
            ],
        },
    )

    transitions = suite.by_category("State Transition")
    # 3 states (pending/paid/shipped) x 2 actions = 6 combinations total: 2 valid + 4 invalid
    positive = [c for c in transitions if "transition" in c.title and "reject" not in c.title]
    negative = [c for c in transitions if "reject" in c.title]
    assert len(positive) == 2
    assert len(negative) == 4


def test_state_cycle_flags_unreachable_state():
    designer = TestDesigner("order-status")
    suite = designer.generate_flow_based_tests(
        "order-status",
        states={
            "initial": "pending",
            "transitions": [
                {"from": "pending", "to": "paid", "action": "complete_payment"},
                # "refunded" only reachable via a transition that doesn't exist from pending/paid
                {"from": "shipped", "to": "refunded", "action": "refund"},
            ],
        },
    )

    regression = suite.by_category("Regression")
    assert any("refunded" in c.title for c in regression)


def test_state_cycle_no_regression_case_when_all_states_reachable():
    designer = TestDesigner("order-status")
    suite = designer.generate_flow_based_tests(
        "order-status",
        states={
            "initial": "pending",
            "transitions": [
                {"from": "pending", "to": "paid", "action": "complete_payment"},
                {"from": "paid", "to": "shipped", "action": "ship_order"},
            ],
        },
    )

    assert suite.by_category("Regression") == []


@pytest.mark.asyncio
async def test_test_generate_fails_fast_for_unknown_feature_without_dimensions():
    result = await generate_tool(feature="checkout")
    assert "error" in result
    assert "example" in result


@pytest.mark.asyncio
async def test_test_generate_login_preset_works_without_fields():
    result = await generate_tool(feature="login")
    assert result["feature"] == "Login"
    assert result["total"] > 0


@pytest.mark.asyncio
async def test_test_generate_api_endpoint_detected_by_prefix():
    result = await generate_tool(feature="/users", method="POST")
    assert "POST /users" in result["feature"]


@pytest.mark.asyncio
async def test_analyze_coverage_requires_fields_for_non_login_feature():
    result = await analyze_coverage_tool(existing_tests=[], feature="checkout")
    assert "error" in result


@pytest.mark.asyncio
async def test_analyze_coverage_reports_missing_categories():
    fields = [{"name": "amount", "type": "number", "required": True}]
    result = await analyze_coverage_tool(
        existing_tests=[{"category": "Positive"}],
        feature="checkout",
        fields=fields,
    )
    assert result["existing_count"] == 1
    assert "Negative" in result["missing_categories"]
