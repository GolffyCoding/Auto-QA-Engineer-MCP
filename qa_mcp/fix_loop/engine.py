"""
Phase 6: Autonomous Fix Loop
วงจร: Discover → Plan → Generate → Execute → Diagnose → Fix → Verify → Regression → Report
มี approval gate ก่อนแก้ source code จริง
"""
import json
import re
import uuid
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime


class FixStatus(Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    VERIFIED = "verified"
    ROLLED_BACK = "rolled_back"


@dataclass
class PatchProposal:
    """ข้อเสนอการแก้ไข"""
    patch_id: str
    failure_id: str
    file_path: str
    original_code: str
    patched_code: str
    description: str
    confidence: float
    status: str = FixStatus.PENDING_APPROVAL.value
    created_at: str = ""
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FixResult:
    """ผลลัพธ์การแก้ไข"""
    patch_id: str
    failure_id: str
    status: str
    test_result: Optional[Dict[str, Any]] = None
    regression_result: Optional[Dict[str, Any]] = None
    applied_at: str = ""
    verified_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FixEngine:
    """Engine สำหรับ autonomous fix loop"""

    def __init__(self, read_only: bool = True, state_path: str = ""):
        from qa_mcp.core.persistence import PersistentStore

        self.read_only = read_only
        self._store = PersistentStore(state_path)
        self._ns = self._store.namespace("patch_proposals")
        self._proposals: Dict[str, PatchProposal] = {
            patch_id: PatchProposal(**data) for patch_id, data in self._ns.items()
        }
        self._results: Dict[str, FixResult] = {}
        self._approval_callbacks: List[Callable] = []

    def _persist(self, proposal: PatchProposal) -> None:
        self._ns[proposal.patch_id] = proposal.to_dict()
        self._store.save()

    def on_approval_required(self, callback: Callable[[PatchProposal], None]):
        """ลงทะเบียน callback เมื่อต้องการ approval"""
        self._approval_callbacks.append(callback)

    async def diagnose(self, failure_evidence: Dict[str, Any]) -> Dict[str, Any]:
        """ขั้นตอน Diagnose"""
        from qa_mcp.failure_analysis.analyzer import FailureEvidence, _analyzer

        evidence = FailureEvidence(**failure_evidence)
        diagnosis = _analyzer.inspect(evidence)

        return {
            "phase": "diagnose",
            "category": diagnosis.category,
            "likely_cause": diagnosis.likely_cause,
            "root_cause": diagnosis.root_cause,
            "confidence": diagnosis.confidence,
            "suggested_fix": diagnosis.suggested_fix,
        }

    async def propose_patch(self, failure_id: str, diagnosis: Dict[str, Any],
                          file_path: str, original_code: str) -> PatchProposal:
        """สร้าง patch proposal จาก diagnosis"""
        category = diagnosis.get("category", "")
        root_cause = diagnosis.get("root_cause", "")

        # สร้าง patched code ตาม category
        patched_code = self._generate_patch(original_code, category, root_cause)

        proposal = PatchProposal(
            patch_id=f"patch-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}",
            failure_id=failure_id,
            file_path=file_path,
            original_code=original_code,
            patched_code=patched_code,
            description=f"Fix {category} issue: {root_cause}",
            confidence=diagnosis.get("confidence", 50.0),
            created_at=datetime.now().isoformat(),
        )

        self._proposals[proposal.patch_id] = proposal
        self._persist(proposal)

        # แจ้ง approval required
        for cb in self._approval_callbacks:
            cb(proposal)

        return proposal

    def _generate_patch(self, original: str, category: str, root_cause: str) -> str:
        """สร้าง patched code (simplified)"""
        patched = original

        if category == "database" and "foreign key" in root_cause.lower():
            # เพิ่ม validation ก่อน insert
            if "def create" in original or "def insert" in original:
                # หาตำแหน่งที่เหมาะสมเพื่อแทรก validation
                lines = original.split("\n")
                new_lines = []
                for i, line in enumerate(lines):
                    new_lines.append(line)
                    if i == 0 and "def " in line:  # หลัง function signature
                        indent = len(line) - len(line.lstrip()) + 4
                        new_lines.append(" " * indent + "# QA-MCP: Added FK validation")
                        new_lines.append(" " * indent + "if not self._validate_foreign_keys(data):")
                        new_lines.append(" " * (indent + 4) + "raise ValueError('Invalid foreign key reference')")
                patched = "\n".join(new_lines)

        elif category == "api" and "500" in root_cause:
            # เพิ่ม error handling
            if "def " in original:
                lines = original.split("\n")
                new_lines = []
                for i, line in enumerate(lines):
                    new_lines.append(line)
                    if i == 0 and "def " in line:
                        indent = len(line) - len(line.lstrip()) + 4
                        new_lines.append(" " * indent + "try:")
                        # indent ทุกบรรทัดที่เหลือ
                        for j in range(i + 1, len(lines)):
                            new_lines.append("    " + lines[j])
                        new_lines.append(" " * indent + "except Exception as e:")
                        new_lines.append(" " * (indent + 4) + f"logger.error(f'Error in {{e}}')")
                        new_lines.append(" " * (indent + 4) + "raise HTTPException(status_code=500, detail='Internal error')")
                        break
                patched = "\n".join(new_lines)

        elif category == "ui":
            # เพิ่ม wait condition
            if "await page.click" in original or "await page.fill" in original:
                patched = original.replace(
                    "await page.click",
                    "await page.wait_for_selector(selector, state='visible')\n    await page.click"
                )

        return patched

    async def request_approval(self, patch_id: str) -> Dict[str, Any]:
        """ขอ approval จาก human"""
        proposal = self._proposals.get(patch_id)
        if not proposal:
            return {"error": "Patch not found"}

        return {
            "patch_id": patch_id,
            "status": "approval_required",
            "file": proposal.file_path,
            "diff": self._generate_diff(proposal.original_code, proposal.patched_code),
            "description": proposal.description,
            "confidence": proposal.confidence,
            "action_required": "Approve or reject this patch",
        }

    def _generate_diff(self, original: str, patched: str) -> str:
        """สร้าง diff แบบง่าย"""
        import difflib
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile="original",
            tofile="patched",
        )
        return "".join(diff)

    async def approve(self, patch_id: str, approved_by: str = "human") -> PatchProposal:
        """อนุมัติ patch"""
        proposal = self._proposals.get(patch_id)
        if proposal:
            proposal.status = FixStatus.APPROVED.value
            proposal.approved_by = approved_by
            proposal.approved_at = datetime.now().isoformat()
            self._persist(proposal)
        return proposal

    async def reject(self, patch_id: str, reason: str = "") -> PatchProposal:
        """ปฏิเสธ patch"""
        proposal = self._proposals.get(patch_id)
        if proposal:
            proposal.status = FixStatus.REJECTED.value
            self._persist(proposal)
        return proposal

    async def apply_patch(self, patch_id: str) -> Dict[str, Any]:
        """Apply patch ลงไฟล์จริง (ถ้าไม่ใช่ read-only)"""
        proposal = self._proposals.get(patch_id)
        if not proposal:
            return {"error": "Patch not found"}

        if proposal.status != FixStatus.APPROVED.value:
            return {"error": "Patch not approved"}

        if self.read_only:
            return {
                "status": "simulated",
                "message": "Read-only mode: patch not applied to filesystem",
                "file": proposal.file_path,
                "would_apply": True,
            }

        # Apply จริง
        try:
            with open(proposal.file_path, "r") as f:
                current = f.read()

            if proposal.original_code in current:
                new_content = current.replace(proposal.original_code, proposal.patched_code)
                with open(proposal.file_path, "w") as f:
                    f.write(new_content)

                proposal.status = FixStatus.APPLIED.value
                self._persist(proposal)
                return {
                    "status": "applied",
                    "file": proposal.file_path,
                    "patch_id": patch_id,
                }
            else:
                return {"error": "Original code not found in file"}
        except Exception as e:
            return {"error": str(e)}

    async def verify(self, patch_id: str, test_command: List[str]) -> FixResult:
        """รัน test หลัง apply patch"""
        from qa_mcp.execution.executor import _executor as executor

        proposal = self._proposals.get(patch_id)
        await executor.create_run(f"verify-{patch_id}")

        result = await executor.run_test(
            test_id=f"verify-{patch_id}",
            test_name=f"Verify fix for {proposal.failure_id}",
            command=test_command,
        )

        fix_result = FixResult(
            patch_id=patch_id,
            failure_id=proposal.failure_id,
            status=FixStatus.VERIFIED.value if result.status == "passed" else FixStatus.PENDING_APPROVAL.value,
            test_result=result.to_dict(),
            applied_at=datetime.now().isoformat(),
            verified_at=datetime.now().isoformat(),
        )

        self._results[patch_id] = fix_result
        return fix_result

    async def run_full_loop(self, failure_evidence: Dict[str, Any],
                           file_path: str,
                           original_code: str,
                           test_command: List[str]) -> Dict[str, Any]:
        """รัน full fix loop"""
        # 1. Diagnose
        diagnosis = await self.diagnose(failure_evidence)

        # 2. Propose
        proposal = await self.propose_patch(
            failure_evidence.get("failure_id", "unknown"),
            diagnosis,
            file_path,
            original_code,
        )

        # 3. Request approval
        approval_req = await self.request_approval(proposal.patch_id)

        return {
            "phase": "fix_loop",
            "diagnosis": diagnosis,
            "proposal": proposal.to_dict(),
            "approval_request": approval_req,
            "next_step": "Wait for human approval, then call fix_loop.apply_patch and fix_loop.verify",
        }


# MCP Tools
# Shared engine so a proposal created by fix_loop.propose is still around
# (in self._proposals) when fix_loop.apply_patch / fix_loop.verify run later
# in the same session, instead of each call getting an empty FixEngine.
_engine = FixEngine(read_only=True)


async def fix_loop_diagnose(failure_evidence: Dict[str, Any]) -> Dict[str, Any]:
    """MCP tool: fix_loop.diagnose"""
    return await _engine.diagnose(failure_evidence)


async def fix_loop_propose(failure_id: str, diagnosis: Dict[str, Any],
                           file_path: str, original_code: str) -> Dict[str, Any]:
    """MCP tool: fix_loop.propose"""
    proposal = await _engine.propose_patch(failure_id, diagnosis, file_path, original_code)
    return proposal.to_dict()


async def fix_loop_approve(patch_id: str, approved_by: str = "human") -> Dict[str, Any]:
    """MCP tool: fix_loop.approve"""
    proposal = await _engine.approve(patch_id, approved_by)
    if proposal is None:
        return {"error": "Patch not found"}
    return proposal.to_dict()


async def fix_loop_apply_patch(patch_id: str, read_only: bool = True) -> Dict[str, Any]:
    """MCP tool: fix_loop.apply_patch

    `read_only=False` ต้องได้รับอนุญาตนอกเหนือจาก LLM agent เอง (env var
    `QA_MCP_ALLOW_AUTO_APPLY=1`) - ไม่งั้น `fix_loop_approve` +
    `fix_loop_apply_patch(read_only=False)` ที่เรียกติดกันโดย LLM ตัวเดียว
    ก็เท่ากับ agent self-approve และ self-apply patch เข้า source code จริง
    โดยไม่มี human ตัวจริงเกี่ยวข้องเลย (approved_by เป็นแค่ string ที่ตั้ง
    เองได้ ไม่ใช่ identity check) การบังคับ env var ทำให้ต้องมีคนตั้งค่านี้
    ไว้ล่วงหน้านอก session ของ agent ถึงจะเปิดโหมดเขียนไฟล์จริงได้
    """
    import os

    if not read_only and os.environ.get("QA_MCP_ALLOW_AUTO_APPLY") != "1":
        return {
            "error": "auto-apply disabled",
            "message": (
                "Applying a patch to the filesystem requires QA_MCP_ALLOW_AUTO_APPLY=1 "
                "to be set in the environment by a human operator ahead of time. "
                "This cannot be enabled by the agent itself from within a tool call."
            ),
        }

    _engine.read_only = read_only
    return await _engine.apply_patch(patch_id)


async def fix_loop_verify(patch_id: str, test_command: List[str]) -> Dict[str, Any]:
    """MCP tool: fix_loop.verify"""
    result = await _engine.verify(patch_id, test_command)
    return result.to_dict()
