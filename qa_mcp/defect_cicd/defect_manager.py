"""
Phase 7: Defect Management
สร้าง defect, attach evidence, link test, link commit
เชื่อม Jira, GitHub Issues, GitLab Issues, Azure DevOps
"""
import json
import os
import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime

import httpx


class DefectSeverity(Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class DefectStatus(Enum):
    NEW = "New"
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    RESOLVED = "Resolved"
    CLOSED = "Closed"
    REOPENED = "Reopened"


@dataclass
class Defect:
    """Defect record"""
    defect_id: str
    title: str
    description: str
    severity: str
    status: str
    test_id: Optional[str] = None
    failure_id: Optional[str] = None
    evidence: List[str] = field(default_factory=list)
    comments: List[Dict[str, str]] = field(default_factory=list)
    linked_commits: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    reporter: str = "qa-mcp"
    assignee: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DefectTracker:
    """จัดการ defects - persist ลงดิสก์จริง (รอด process restart)"""

    def __init__(self, state_path: Optional[str] = None):
        from qa_mcp.core.persistence import PersistentStore

        self._store = PersistentStore(state_path or "")
        self._ns = self._store.namespace("defects")
        self._defects: Dict[str, Defect] = {
            defect_id: Defect(**data) for defect_id, data in self._ns.items()
        }

    def _persist(self, defect: Defect) -> None:
        self._ns[defect.defect_id] = defect.to_dict()
        self._store.save()

    async def create(self, title: str, description: str,
                   severity: str = DefectSeverity.HIGH.value,
                   test_id: Optional[str] = None,
                   failure_id: Optional[str] = None) -> Defect:
        """สร้าง defect ใหม่"""
        # timestamp เพื่อให้อ่าน/sort ง่าย + random suffix กัน collision เวลา
        # สร้างพร้อมกันหลาย defect ภายใน 1 วินาทีเดียวกัน (เช่นหลาย engineer/
        # หลาย automated run พร้อมกัน - ของเดิมชนกันจริงเวลาเกิดพร้อมกัน)
        defect_id = f"BUG-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        now = datetime.now().isoformat()

        defect = Defect(
            defect_id=defect_id,
            title=title,
            description=description,
            severity=severity,
            status=DefectStatus.NEW.value,
            test_id=test_id,
            failure_id=failure_id,
            created_at=now,
            updated_at=now,
        )

        self._defects[defect_id] = defect
        self._persist(defect)
        return defect

    async def attach_evidence(self, defect_id: str, evidence_path: str) -> Defect:
        """แนบ evidence"""
        defect = self._defects.get(defect_id)
        if defect:
            defect.evidence.append(evidence_path)
            defect.updated_at = datetime.now().isoformat()
            self._persist(defect)
        return defect

    async def add_comment(self, defect_id: str, author: str, text: str) -> Defect:
        """เพิ่ม comment"""
        defect = self._defects.get(defect_id)
        if defect:
            defect.comments.append({
                "author": author,
                "text": text,
                "timestamp": datetime.now().isoformat(),
            })
            defect.updated_at = datetime.now().isoformat()
            self._persist(defect)
        return defect

    async def link_test(self, defect_id: str, test_id: str) -> Defect:
        """เชื่อมโยง test"""
        defect = self._defects.get(defect_id)
        if defect:
            defect.test_id = test_id
            defect.updated_at = datetime.now().isoformat()
            self._persist(defect)
        return defect

    async def link_commit(self, defect_id: str, commit_hash: str) -> Defect:
        """เชื่อม commit"""
        defect = self._defects.get(defect_id)
        if defect:
            defect.linked_commits.append(commit_hash)
            defect.updated_at = datetime.now().isoformat()
            self._persist(defect)
        return defect

    async def update_status(self, defect_id: str, status: str) -> Defect:
        """อัปเดตสถานะ"""
        defect = self._defects.get(defect_id)
        if defect:
            defect.status = status
            defect.updated_at = datetime.now().isoformat()
            self._persist(defect)
        return defect

    def get(self, defect_id: str) -> Optional[Defect]:
        return self._defects.get(defect_id)

    def list_all(self) -> List[Defect]:
        return list(self._defects.values())


class JiraIntegration:
    """Jira integration (stub)"""

    def __init__(self, base_url: str, username: str, token: str):
        self.base_url = base_url
        self.username = username
        self.token = token

    async def create_issue(self, project_key: str, summary: str,
                           description: str, issue_type: str = "Bug") -> Dict[str, Any]:
        """สร้าง Jira issue"""
        # ใน production จะ call Jira API จริง
        return {
            "key": f"{project_key}-123",
            "summary": summary,
            "status": "Open",
            "url": f"{self.base_url}/browse/{project_key}-123",
        }

    async def attach_file(self, issue_key: str, file_path: str) -> Dict[str, Any]:
        return {"success": True, "issue": issue_key, "file": file_path}


class GitHubIntegration:
    """GitHub integration"""

    def __init__(self, token: str):
        self.token = token

    async def create_issue(self, repo: str, title: str, body: str,
                           labels: Optional[List[str]] = None) -> Dict[str, Any]:
        # ใน production จะ call GitHub API จริง
        return {
            "number": 42,
            "title": title,
            "url": f"https://github.com/{repo}/issues/42",
        }

    async def create_pr(self, repo: str, title: str, body: str,
                        head: str, base: str = "main") -> Dict[str, Any]:
        return {
            "number": 43,
            "title": title,
            "url": f"https://github.com/{repo}/pull/43",
        }


class GitManager:
    """Git operations"""

    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path

    async def status(self) -> Dict[str, Any]:
        """Git status"""
        import subprocess
        result = subprocess.run(
            ["git", "-C", self.repo_path, "status", "--short"],
            capture_output=True,
            text=True,
        )
        return {
            "modified": [l.strip() for l in result.stdout.splitlines() if l.startswith(" M")],
            "untracked": [l.strip() for l in result.stdout.splitlines() if l.startswith("??")],
        }

    async def diff(self) -> str:
        """Git diff"""
        import subprocess
        result = subprocess.run(
            ["git", "-C", self.repo_path, "diff"],
            capture_output=True,
            text=True,
        )
        return result.stdout

    async def log(self, n: int = 5) -> List[Dict[str, str]]:
        """Git log"""
        import subprocess
        result = subprocess.run(
            ["git", "-C", self.repo_path, "log", f"--max-count={n}",
             "--pretty=format:%H|%s|%an|%ad"],
            capture_output=True,
            text=True,
        )
        commits = []
        for line in result.stdout.splitlines():
            parts = line.split("|", 3)
            if len(parts) >= 3:
                commits.append({
                    "hash": parts[0],
                    "message": parts[1],
                    "author": parts[2],
                })
        return commits

    async def create_branch(self, branch_name: str) -> Dict[str, Any]:
        """สร้าง branch ใหม่"""
        import subprocess
        subprocess.run(
            ["git", "-C", self.repo_path, "checkout", "-b", branch_name],
            capture_output=True,
        )
        return {"branch": branch_name, "status": "created"}

    async def commit(self, message: str, files: Optional[List[str]] = None) -> Dict[str, Any]:
        """Commit changes"""
        import subprocess
        if files:
            subprocess.run(["git", "-C", self.repo_path, "add"] + files, capture_output=True)
        else:
            subprocess.run(["git", "-C", self.repo_path, "add", "-A"], capture_output=True)
        result = subprocess.run(
            ["git", "-C", self.repo_path, "commit", "-m", message],
            capture_output=True,
            text=True,
        )
        return {"success": result.returncode == 0, "output": result.stdout}


class CIManager:
    """CI/CD integration - trigger pipeline จริงผ่าน REST API ของ provider
    (ไม่ใช่ stub ที่ return fake success เหมือนเดิม)

    ต้องมี auth token จริง:
    - GitHub Actions: env var `GITHUB_TOKEN` (fine-grained PAT พร้อม
      `actions:write`) + ต้องระบุ `repo` เป็น "owner/name"
    - GitLab CI: env var `GITLAB_TRIGGER_TOKEN` (pipeline trigger token) +
      `GITLAB_API_TOKEN` (สำหรับ get_status) + ต้องระบุ `repo` เป็น project ID
    """

    def detect(self, project_path: str = ".") -> str:
        """ตรวจหา CI/CD provider"""
        if os.path.exists(os.path.join(project_path, ".github", "workflows")):
            return "github_actions"
        elif os.path.exists(os.path.join(project_path, ".gitlab-ci.yml")):
            return "gitlab_ci"
        elif os.path.exists(os.path.join(project_path, "Jenkinsfile")):
            return "jenkins"
        elif os.path.exists(os.path.join(project_path, "azure-pipelines.yml")):
            return "azure_devops"
        return "unknown"

    async def run(
        self, provider: str, pipeline: str, repo: Optional[str] = None,
        ref: str = "main", inputs: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Trigger pipeline จริง - pipeline คือ workflow filename (GitHub) หรือไม่ใช้ (GitLab)"""
        if provider == "github_actions":
            return await self._run_github(pipeline, repo, ref, inputs or {})
        if provider == "gitlab_ci":
            return await self._run_gitlab(repo, ref, inputs or {})
        return {"error": f"ci.run ยังไม่รองรับ provider '{provider}' - รองรับเฉพาะ github_actions, gitlab_ci ตอนนี้"}

    async def _run_github(self, workflow_file: str, repo: Optional[str], ref: str, inputs: Dict[str, str]) -> Dict[str, Any]:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            return {"error": "ต้องตั้งค่า environment variable GITHUB_TOKEN ก่อนใช้ ci.run กับ GitHub Actions"}
        if not repo:
            return {"error": "ต้องระบุ 'repo' เป็น \"owner/name\" สำหรับ GitHub Actions"}

        url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/dispatches"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json={"ref": ref, "inputs": inputs},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            )
        if resp.status_code == 204:
            return {"provider": "github_actions", "pipeline": workflow_file, "repo": repo, "ref": ref, "status": "triggered"}
        return {"provider": "github_actions", "status": "error", "http_status": resp.status_code, "detail": resp.text[:500]}

    async def _run_gitlab(self, project_id: Optional[str], ref: str, inputs: Dict[str, str]) -> Dict[str, Any]:
        token = os.environ.get("GITLAB_TRIGGER_TOKEN")
        if not token or not project_id:
            return {"error": "ต้องตั้งค่า GITLAB_TRIGGER_TOKEN และระบุ 'repo' เป็น GitLab project ID"}

        url = f"https://gitlab.com/api/v4/projects/{project_id}/trigger/pipeline"
        data = {"token": token, "ref": ref}
        for key, value in inputs.items():
            data[f"variables[{key}]"] = value

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=data)
        if resp.status_code == 201:
            body = resp.json()
            return {"provider": "gitlab_ci", "status": "triggered", "run_id": str(body.get("id")), "web_url": body.get("web_url")}
        return {"provider": "gitlab_ci", "status": "error", "http_status": resp.status_code, "detail": resp.text[:500]}

    async def get_status(self, provider: str, run_id: str, repo: Optional[str] = None) -> Dict[str, Any]:
        """เช็คสถานะ pipeline run จริงผ่าน API"""
        if provider == "github_actions":
            token = os.environ.get("GITHUB_TOKEN")
            if not token or not repo:
                return {"error": "ต้องตั้งค่า GITHUB_TOKEN และระบุ 'repo'"}
            url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
            if resp.status_code == 200:
                body = resp.json()
                return {"provider": provider, "run_id": run_id, "status": body.get("status"),
                        "conclusion": body.get("conclusion"), "html_url": body.get("html_url")}
            return {"provider": provider, "status": "error", "http_status": resp.status_code, "detail": resp.text[:300]}

        if provider == "gitlab_ci":
            token = os.environ.get("GITLAB_API_TOKEN")
            if not token or not repo:
                return {"error": "ต้องตั้งค่า GITLAB_API_TOKEN และระบุ 'repo' เป็น project ID"}
            url = f"https://gitlab.com/api/v4/projects/{repo}/pipelines/{run_id}"
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers={"PRIVATE-TOKEN": token})
            if resp.status_code == 200:
                body = resp.json()
                return {"provider": provider, "run_id": run_id, "status": body.get("status"), "web_url": body.get("web_url")}
            return {"provider": provider, "status": "error", "http_status": resp.status_code, "detail": resp.text[:300]}

        return {"error": f"unsupported provider '{provider}'"}


# MCP Tools
# Shared singletons so defect.create → defect.attach_evidence (and the git/CI
# tools) operate on the same tracker/repo state within a running process,
# instead of each call getting a throwaway in-memory tracker.
_tracker = DefectTracker()


async def defect_create(title: str, description: str, severity: str = "High") -> Dict[str, Any]:
    """MCP tool: defect.create"""
    defect = await _tracker.create(title, description, severity)
    return defect.to_dict()


async def defect_attach_evidence(defect_id: str, evidence_path: str) -> Dict[str, Any]:
    """MCP tool: defect.attach_evidence"""
    tracker = _tracker
    defect = await tracker.attach_evidence(defect_id, evidence_path)
    return defect.to_dict()


async def git_status() -> Dict[str, Any]:
    """MCP tool: git.status"""
    manager = GitManager()
    return await manager.status()


async def git_diff() -> str:
    """MCP tool: git.diff"""
    manager = GitManager()
    return await manager.diff()


async def git_create_branch(branch_name: str) -> Dict[str, Any]:
    """MCP tool: git.create_branch"""
    manager = GitManager()
    return await manager.create_branch(branch_name)


async def git_commit(message: str) -> Dict[str, Any]:
    """MCP tool: git.commit"""
    manager = GitManager()
    return await manager.commit(message)


_ci_manager = CIManager()


async def ci_detect() -> str:
    """MCP tool: ci.detect"""
    return _ci_manager.detect()


async def ci_run(
    pipeline: str, repo: Optional[str] = None, ref: str = "main",
    inputs: Optional[Dict[str, str]] = None, provider: Optional[str] = None,
) -> Dict[str, Any]:
    """MCP tool: ci.run - trigger CI pipeline จริง (ต้องมี GITHUB_TOKEN หรือ
    GITLAB_TRIGGER_TOKEN ใน environment - ดู CIManager docstring)

    provider: ระบุตรง ๆ ("github_actions"/"gitlab_ci") ถ้าต่างจากที่
    ci.detect() เจอในเครื่องที่รัน qa-mcp-serve เอง (เช่น qa-mcp-serve รันอยู่
    server กลาง แต่ repo เป้าหมายเป็นคนละที่)
    """
    provider = provider or _ci_manager.detect()
    return await _ci_manager.run(provider, pipeline, repo=repo, ref=ref, inputs=inputs)


async def ci_get_status(run_id: str, repo: Optional[str] = None, provider: Optional[str] = None) -> Dict[str, Any]:
    """MCP tool: ci.get_status - เช็คสถานะ pipeline run จริงผ่าน API"""
    provider = provider or _ci_manager.detect()
    return await _ci_manager.get_status(provider, run_id, repo=repo)
