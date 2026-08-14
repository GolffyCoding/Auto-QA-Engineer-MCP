"""Unit tests for qa_mcp.knowledge.concepts - static QA reference material
(adapted from StrongQA's knowledge base) an agent can look up instead of
guessing/hallucinating textbook QA theory. Pure data lookups, no state.
"""
import pytest

from qa_mcp.knowledge.concepts import (
    CONCEPTS,
    TESTING_TYPES,
    knowledge_get_concept,
    knowledge_list_concepts,
    knowledge_get_testing_type,
    knowledge_list_testing_types,
)


def test_all_six_key_concepts_present():
    expected = {
        "software_testing", "testing_qa_qc", "testing_vs_debugging",
        "verification_vs_validation", "testing_documentation", "myths_about_qa",
    }
    assert expected.issubset(CONCEPTS.keys())


def test_all_five_testing_types_present():
    expected = {"functional", "performance", "load", "stress", "stability"}
    assert expected.issubset(TESTING_TYPES.keys())


@pytest.mark.asyncio
async def test_get_concept_returns_title_and_summary():
    result = await knowledge_get_concept("verification_vs_validation")
    assert result["title"] == "Verification vs Validation"
    assert "verification" in result["summary"].lower()
    assert "validation" in result["summary"].lower()
    assert result["source"].startswith("https://strongqa.com")


@pytest.mark.asyncio
async def test_get_concept_unknown_topic_lists_available():
    result = await knowledge_get_concept("nonexistent_topic")
    assert "error" in result
    assert "software_testing" in result["available"]


@pytest.mark.asyncio
async def test_list_concepts_returns_all_topics():
    concepts = await knowledge_list_concepts()
    topics = {c["topic"] for c in concepts}
    assert "myths_about_qa" in topics
    assert len(concepts) == len(CONCEPTS)


@pytest.mark.asyncio
async def test_get_testing_type_stress_mentions_breaking_point():
    result = await knowledge_get_testing_type("stress")
    assert result["title"] == "Stress Testing"
    assert "break" in result["summary"].lower()


@pytest.mark.asyncio
async def test_get_testing_type_unknown_lists_available():
    result = await knowledge_get_testing_type("bogus")
    assert "error" in result
    assert "load" in result["available"]


@pytest.mark.asyncio
async def test_list_testing_types_returns_all():
    types = await knowledge_list_testing_types()
    names = {t["type"] for t in types}
    assert names == set(TESTING_TYPES.keys())
