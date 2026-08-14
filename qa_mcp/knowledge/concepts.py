"""
QA reference concepts - grounded definitions an agent can look up instead
of guessing or hallucinating textbook QA theory. Content adapted from
StrongQA's QA knowledge base (https://strongqa.com/qa-portal/knowledge-base),
kept as structured data (not a document dump) so an agent can pull exactly
the concept it needs.

This is reference material, separate from qa_mcp.knowledge.base.KnowledgeBase
(which holds *your* company/project-specific conventions) - concepts here
are general QA theory that doesn't change per project.
"""
from typing import Any, Dict, List, Optional

CONCEPTS: Dict[str, Dict[str, str]] = {
    "software_testing": {
        "title": "Software Testing",
        "summary": (
            "The process of evaluating a system or its component(s) to determine whether it "
            "meets specified requirements - executing a system to identify errors, gaps, or "
            "missing requirements against what was specified. Per ANSI/IEEE 1059: a process of "
            "analyzing a software item to detect discrepancies between actual and required "
            "conditions (errors/bugs/defects) and to estimate the software item's features."
        ),
        "source": "https://strongqa.com/qa-portal/knowledge-base/key-concepts/software-testing",
    },
    "testing_qa_qc": {
        "title": "Testing, QA, and QC",
        "summary": (
            "Three related but distinct activities. Testing detects bugs in a product through "
            "execution and test planning. Quality Control (QC) is an independent inspection "
            "process before delivery - it analyzes the product to judge its quality and can, in "
            "principle, work with minimal testing. Quality Assurance (QA) is broader: a system "
            "of methods that guarantees product quality by engineering processes that prevent "
            "defects from recurring - QA may not involve testing at all. The most effective "
            "quality approach combines all three."
        ),
        "source": "https://strongqa.com/qa-portal/knowledge-base/key-concepts/testing-qa-and-qc",
    },
    "testing_vs_debugging": {
        "title": "Testing vs Debugging",
        "summary": (
            "Testing identifies software defects without correcting them - typically done by a "
            "QA team during the testing phase. Debugging goes further: identifying, isolating, "
            "and fixing bugs - typically done by developers during development or when "
            "addressing a reported issue. Testing stops at 'here's a defect'; debugging covers "
            "finding root cause and implementing a fix."
        ),
        "source": "https://strongqa.com/qa-portal/knowledge-base/key-concepts/testing-vs-debugging",
    },
    "verification_vs_validation": {
        "title": "Verification vs Validation",
        "summary": (
            "Verification happens near the start of the development phase and asks 'did we "
            "build the product according to the initial specification?' Validation happens near "
            "the end and asks 'does the product meet the actual requirement / what the customer "
            "needs?' Verification checks the team built things correctly; validation checks they "
            "built the right thing."
        ),
        "source": "https://strongqa.com/qa-portal/knowledge-base/key-concepts/verification-vs-validation",
    },
    "testing_documentation": {
        "title": "Testing Documentation",
        "summary": (
            "Artifacts produced before/during testing to plan effort, track requirements, and "
            "measure coverage. Four main types: (1) Test Plan - the overall strategy, scope, "
            "resources, environment, and schedule, usually written by a QA lead; (2) Test Case - "
            "a concrete set of inputs, steps, and conditions with expected/actual outcomes used "
            "to verify one piece of functionality; (3) Test Scenario - a one-line statement of "
            "what area of the application will be tested, often covering a multi-step flow where "
            "each step depends on the previous one; (4) Requirements Traceability Matrix (RTM) - "
            "a table linking each requirement to its test cases and bug IDs, used to verify "
            "coverage against spec and trace root cause."
        ),
        "source": "https://strongqa.com/qa-portal/knowledge-base/key-concepts/testing-documentation",
    },
    "myths_about_qa": {
        "title": "Myths about QA",
        "summary": (
            "Ten common misconceptions: (1) testing IS QA - testing is only one part of QA, "
            "which spans the whole development process; (2) all bugs can be eliminated - every "
            "system has bugs, the realistic goal is an acceptable defect level; (3) testing "
            "should be fully automated - automation complements manual testing, it doesn't "
            "replace the unpredictable inputs and judgment a human tester brings; (4) testing is "
            "easy - it requires real technique and domain expertise; (5) only QA teams test - "
            "quality is a shared responsibility, not just the testers' job; (6) more testing "
            "always improves quality - 100% coverage is unrealistic, risk-based prioritization "
            "beats exhaustive testing; (7) testing happens at the end of a project - late testing "
            "means rushed schedules and expensive fixes; (8) performance testing belongs only in "
            "production - it should be integrated throughout development; (9) security and "
            "quality testing are separate - security needs continuous integration via design and "
            "code review, not a last-minute pass; (10) QA is expensive - skimping on it is a "
            "false economy, since inadequate testing causes far costlier failures later."
        ),
        "source": "https://strongqa.com/qa-portal/knowledge-base/key-concepts/myths-about-qa",
    },
}

TESTING_TYPES: Dict[str, Dict[str, str]] = {
    "functional": {
        "title": "Functional Testing",
        "summary": (
            "Testing aimed at checking whether the software can do the tasks users actually "
            "need - functional suitability (does it do its core job), accuracy (are outcomes "
            "correct within an acceptable margin), interoperability (does it integrate with "
            "other systems without manual intervention), compliance (does it meet applicable "
            "standards/regulations), and security (can it resist unauthorized access/attacks). "
            "Runs closest to real customer conditions (OS/browser/DB), so it's usually the "
            "highest-value target for automation - but it can miss purely logical mistakes and "
            "risks redundant coverage if not scoped carefully. This is what "
            "qa_mcp.test_design.generator's Positive/Negative/Boundary/Security categories cover."
        ),
        "source": "https://strongqa.com/qa-portal/knowledge-base/testing-types/functional-testing",
    },
    "performance": {
        "title": "Performance Testing",
        "summary": (
            "Testing that determines how a system performs under a given workload - "
            "responsiveness, stability, scalability, reliability, resource usage. Three main "
            "categories: Load Testing (expected concurrent-user volume), Stress Testing "
            "(beyond capacity, to find the breaking point), and Capacity Testing (the point "
            "where response times become unacceptable). Sub-genres: Volume Testing (how much "
            "data the app can handle), Spike Testing (sudden surge/drop in users), and Soak/"
            "Stability Testing (sustained load over an extended period). See "
            "`api.load_test`'s `test_type` parameter, which implements load/stress/stability/"
            "spike as real k6 execution patterns."
        ),
        "source": "https://strongqa.com/qa-portal/knowledge-base/testing-types/performance-testing",
    },
    "load": {
        "title": "Load Testing",
        "summary": (
            "Evaluates behavior under increasing load (concurrent users and/or transactions) to "
            "determine what load the system can actually handle, and whether it still meets its "
            "SLA response-time/throughput targets. Not trying to break the system (that's stress "
            "testing) - trying to confirm it holds up under realistic, expected demand. "
            "`api.load_test(test_type=\"load\")` (the default) runs a flat number of virtual "
            "users for a fixed duration/iteration count."
        ),
        "source": "https://strongqa.com/qa-portal/knowledge-base/testing-types/performance-testing/load-testing",
    },
    "stress": {
        "title": "Stress Testing",
        "summary": (
            "Evaluates a system at or beyond the limits of its anticipated workload, or with "
            "reduced resources (memory, server capacity), emphasizing robustness and error "
            "handling under heavy load rather than correctness under normal conditions. Goal: "
            "surface bugs that only appear under high load - synchronization issues, memory "
            "leaks, race conditions - and find the actual breaking point. "
            "`api.load_test(test_type=\"stress\")` ramps virtual users up in stages well beyond "
            "the requested `vus` instead of holding a flat load."
        ),
        "source": "https://strongqa.com/qa-portal/knowledge-base/testing-types/performance-testing/stress-testing",
    },
    "stability": {
        "title": "Stability Testing (Soak/Endurance Testing)",
        "summary": (
            "Determines whether the software can keep performing its required functions under "
            "specified conditions for an extended period without a break - no memory leaks, no "
            "unexpected restarts, no degradation over time. Distinct from reliability (which "
            "measures consistency of repeated results); stability is specifically a time-varying "
            "attribute measured by monitoring over a sustained run. "
            "`api.load_test(test_type=\"stability\")` holds a constant, moderate load for a "
            "much longer duration than a standard load test."
        ),
        "source": "https://strongqa.com/qa-portal/knowledge-base/testing-types/performance-testing/stability-testing",
    },
}


def get_concept(topic: str) -> Optional[Dict[str, str]]:
    return CONCEPTS.get(topic)


def get_testing_type(type_name: str) -> Optional[Dict[str, str]]:
    return TESTING_TYPES.get(type_name)


# MCP Tools
async def knowledge_get_concept(topic: str) -> Dict[str, Any]:
    """MCP tool: knowledge.get_concept - ดึงคำนิยาม/คำอธิบายของ QA concept พื้นฐาน
    (เช่น "testing_vs_debugging", "verification_vs_validation") เพื่อไม่ให้ agent
    ต้องเดา/hallucinate ทฤษฎี QA เอง เรียก knowledge.list_concepts เพื่อดู topic
    ที่มีทั้งหมด
    """
    concept = get_concept(topic)
    if concept is None:
        return {"error": f"Unknown concept '{topic}'", "available": list(CONCEPTS.keys())}
    return concept


async def knowledge_list_concepts() -> List[Dict[str, str]]:
    """MCP tool: knowledge.list_concepts - ดูรายชื่อ QA concept ทั้งหมดที่มีคำนิยามพร้อมใช้"""
    return [{"topic": k, "title": v["title"]} for k, v in CONCEPTS.items()]


async def knowledge_get_testing_type(type_name: str) -> Dict[str, Any]:
    """MCP tool: knowledge.get_testing_type - ดึงคำนิยามของ testing type (เช่น
    "load", "stress", "stability", "functional", "performance") เรียก
    knowledge.list_testing_types เพื่อดูทั้งหมด
    """
    testing_type = get_testing_type(type_name)
    if testing_type is None:
        return {"error": f"Unknown testing type '{type_name}'", "available": list(TESTING_TYPES.keys())}
    return testing_type


async def knowledge_list_testing_types() -> List[Dict[str, str]]:
    """MCP tool: knowledge.list_testing_types - ดูรายชื่อ testing type ทั้งหมดที่มีคำนิยามพร้อมใช้"""
    return [{"type": k, "title": v["title"]} for k, v in TESTING_TYPES.items()]
