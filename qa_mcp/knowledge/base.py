"""
Knowledge Base - engineering memory for company/project-specific QA
conventions, so the LLM doesn't have to be re-taught the same context
every session: "we use Playwright not Selenium", "our staging URL is X",
"a 'concurrency' failure on the checkout service is almost always the
inventory-lock bug, fix by retrying with backoff", etc.

Persists through the same PersistentStore every other stateful module in
this project uses (qa_mcp/core/persistence.py) - atomic writes, safe for
concurrent writers, survives a qa-mcp-serve restart. `create_server()` in
qa_mcp/server.py reads `project_rules` from here at startup and folds them
into the instructions the LLM sees on connection, so rules added once are
automatically visible in every future session without the agent having to
call a tool to fetch them first.
"""
from typing import Dict, List, Optional, Any
from datetime import datetime


class KnowledgeBase:
    """Company/project-specific QA memory - rules, failure patterns, decisions"""

    def __init__(self, state_path: str = ""):
        from qa_mcp.core.persistence import PersistentStore

        self._store = PersistentStore(state_path)
        self._rules_ns = self._store.namespace("knowledge_rules")
        self._failures_ns = self._store.namespace("knowledge_failure_patterns")
        self._decisions_ns = self._store.namespace("knowledge_decisions")

    def add_failure_pattern(self, pattern: str, fix: str, confidence: float = 0.8) -> Dict[str, Any]:
        """บันทึก failure pattern เฉพาะของโปรเจกต์/บริษัทนี้ (เช่น "connection pool
        exhausted บน checkout service" มักเกิดจาก retry storm ไม่ใช่ database
        จริง ๆ) - เพิ่มเติมจาก pattern ทั่วไปที่ failure_analysis รู้อยู่แล้ว
        """
        entry = {
            "pattern": pattern,
            "fix": fix,
            "confidence": confidence,
            "timestamp": datetime.now().isoformat(),
        }
        key = f"{len(self._failures_ns)}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        self._failures_ns[key] = entry
        self._store.save()
        return entry

    def get_similar_failures(self, error_message: str) -> List[Dict[str, Any]]:
        """หา failure pattern เฉพาะของโปรเจกต์นี้ที่คล้ายกับ error message ที่ให้มา"""
        error_lower = error_message.lower()
        return [fh for fh in self._failures_ns.values() if fh["pattern"].lower() in error_lower]

    def add_project_rule(self, rule_name: str, rule: str) -> Dict[str, Any]:
        """บันทึก convention เฉพาะของโปรเจกต์/บริษัทนี้ (เช่น "target_framework
        default คือ playwright ไม่ใช่ selenium", "staging URL คือ ...") - ทุก
        rule ที่บันทึกไว้จะถูกใส่เข้า instructions ของ qa-mcp-serve อัตโนมัติ
        ตั้งแต่ connect ครั้งต่อไป ไม่ต้องบอก LLM ซ้ำทุกเซสชัน
        """
        entry = {"rule": rule, "added_at": datetime.now().isoformat()}
        self._rules_ns[rule_name] = entry
        self._store.save()
        return entry

    def get_project_rules(self) -> Dict[str, Any]:
        return dict(self._rules_ns)

    def add_decision(self, context: str, decision: str, rationale: str) -> Dict[str, Any]:
        """บันทึกการตัดสินใจเชิง QA ของทีม (เช่น "ไม่ทำ visual regression testing
        เพราะ design เปลี่ยนบ่อยเกินไป") พร้อมเหตุผล ให้ agent ในอนาคตเข้าใจบริบท
        แทนที่จะเสนอสิ่งที่ทีมตัดสินใจไม่ทำไปแล้วซ้ำ ๆ
        """
        entry = {
            "context": context,
            "decision": decision,
            "rationale": rationale,
            "timestamp": datetime.now().isoformat(),
        }
        key = f"{len(self._decisions_ns)}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        self._decisions_ns[key] = entry
        self._store.save()
        return entry

    def get_decisions(self) -> List[Dict[str, Any]]:
        return list(self._decisions_ns.values())


_kb = KnowledgeBase()


# MCP Tools
async def knowledge_add_rule(rule_name: str, rule: str) -> Dict[str, Any]:
    """MCP tool: knowledge.add_rule - บันทึก project/company convention ที่ agent
    ควรรู้ทุกเซสชัน (เช่น "default browser framework คือ playwright", "auth
    ใช้ JWT ไม่ใช่ session cookie") - เพิ่มครั้งเดียว แล้วจะถูกใส่เข้า instructions
    ของ qa-mcp-serve อัตโนมัติทุกครั้งที่ agent ต่อเข้ามาใหม่ (ดู qa_mcp/server.py)
    """
    return _kb.add_project_rule(rule_name, rule)


async def knowledge_get_rules() -> Dict[str, Any]:
    """MCP tool: knowledge.get_rules - ดู project rule ทั้งหมดที่บันทึกไว้"""
    return _kb.get_project_rules()


async def knowledge_add_failure_pattern(pattern: str, fix: str, confidence: float = 0.8) -> Dict[str, Any]:
    """MCP tool: knowledge.add_failure_pattern - บันทึก failure pattern เฉพาะของ
    โปรเจกต์นี้ (เสริมจาก 15 category ทั่วไปที่ failure_analysis รู้อยู่แล้ว)
    """
    return _kb.add_failure_pattern(pattern, fix, confidence)


async def knowledge_get_similar_failures(error_message: str) -> List[Dict[str, Any]]:
    """MCP tool: knowledge.get_similar_failures - หา failure pattern เฉพาะของ
    โปรเจกต์นี้ที่เคยเจอคล้ายกับ error message นี้มาก่อน
    """
    return _kb.get_similar_failures(error_message)


async def knowledge_add_decision(context: str, decision: str, rationale: str) -> Dict[str, Any]:
    """MCP tool: knowledge.add_decision - บันทึกการตัดสินใจเชิง QA ของทีมพร้อม
    เหตุผล กัน agent เสนอสิ่งที่ทีมตัดสินใจไม่ทำไปแล้วซ้ำ ๆ
    """
    return _kb.add_decision(context, decision, rationale)


async def knowledge_get_decisions() -> List[Dict[str, Any]]:
    """MCP tool: knowledge.get_decisions - ดูการตัดสินใจเชิง QA ที่ทีมบันทึกไว้ทั้งหมด"""
    return _kb.get_decisions()
