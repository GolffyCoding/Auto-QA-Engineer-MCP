"""
Knowledge Base
เก็บ engineering memory สำหรับ QA
"""
import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime


class KnowledgeBase:
    """Knowledge base สำหรับ QA memory"""

    def __init__(self, storage_path: str = "./qa-knowledge.json"):
        self.storage_path = storage_path
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.storage_path):
            with open(self.storage_path, "r") as f:
                return json.load(f)
        return {
            "project_rules": {},
            "test_history": [],
            "failure_history": [],
            "decisions": [],
            "patterns": {},
        }

    def _save(self):
        with open(self.storage_path, "w") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def add_failure_pattern(self, pattern: str, fix: str, confidence: float = 0.8):
        """เพิ่ม failure pattern"""
        self._data["failure_history"].append({
            "pattern": pattern,
            "fix": fix,
            "confidence": confidence,
            "timestamp": datetime.now().isoformat(),
        })
        self._save()

    def get_similar_failures(self, error_message: str) -> List[Dict[str, Any]]:
        """หา failure ที่คล้ายกัน"""
        similar = []
        for fh in self._data["failure_history"]:
            if fh["pattern"].lower() in error_message.lower():
                similar.append(fh)
        return similar

    def add_project_rule(self, rule_name: str, rule: str):
        """เพิ่ม project rule"""
        self._data["project_rules"][rule_name] = {
            "rule": rule,
            "added_at": datetime.now().isoformat(),
        }
        self._save()

    def get_project_rules(self) -> Dict[str, Any]:
        return self._data["project_rules"]

    def add_decision(self, context: str, decision: str, rationale: str):
        """บันทึกการตัดสินใจ"""
        self._data["decisions"].append({
            "context": context,
            "decision": decision,
            "rationale": rationale,
            "timestamp": datetime.now().isoformat(),
        })
        self._save()
