"""
Phase 1: Project Intelligence
ให้ LLM เข้าใจ project ก่อนเริ่มทดสอบ
"""
import os
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum


class FrameworkType(Enum):
    NEXTJS = "Next.js"
    REACT = "React"
    VUE = "Vue"
    ANGULAR = "Angular"
    DJANGO = "Django"
    FLASK = "Flask"
    FASTAPI = "FastAPI"
    EXPRESS = "Express"
    SPRING = "Spring Boot"
    LARAVEL = "Laravel"
    RAILS = "Ruby on Rails"
    UNKNOWN = "Unknown"


class DatabaseType(Enum):
    POSTGRESQL = "PostgreSQL"
    MYSQL = "MySQL"
    MONGODB = "MongoDB"
    SQLITE = "SQLite"
    REDIS = "Redis"
    UNKNOWN = "Unknown"


class AuthType(Enum):
    JWT = "JWT"
    SESSION = "Session"
    OAUTH2 = "OAuth2"
    BASIC = "Basic Auth"
    UNKNOWN = "Unknown"


@dataclass
class ProjectProfile:
    """Profile ของ project ที่ scan ได้"""
    name: str
    framework: str
    language: str
    database: str
    api_style: str
    auth: str
    testing_tools: List[str]
    routes: List[str]
    api_endpoints: List[Dict[str, Any]]
    components: List[str]
    forms: List[str]
    dependencies: Dict[str, str]
    has_tests: bool
    ci_cd: Optional[str] = None


class ProjectScanner:
    """สแกน project เพื่อสร้าง intelligence ให้ LLM"""

    FRAMEWORK_INDICATORS = {
        FrameworkType.NEXTJS: ["next.config", "next/head", "next/router"],
        FrameworkType.REACT: ["react-dom", "create-react-app", "vite.config"],
        FrameworkType.VUE: ["vue.config", "@vue"],
        FrameworkType.ANGULAR: ["angular.json", "@angular"],
        FrameworkType.DJANGO: ["settings.py", "wsgi.py", "manage.py"],
        FrameworkType.FLASK: ["Flask", "app.py", "flask"],
        FrameworkType.FASTAPI: ["FastAPI", "fastapi"],
        FrameworkType.EXPRESS: ["express", "app.js"],
        FrameworkType.SPRING: ["pom.xml", "build.gradle", "@SpringBootApplication"],
        FrameworkType.LARAVEL: ["artisan", "laravel"],
        FrameworkType.RAILS: ["Gemfile", "rails", "config/routes.rb"],
    }

    DB_INDICATORS = {
        DatabaseType.POSTGRESQL: ["pg", "postgres", "psycopg", "postgresql"],
        DatabaseType.MYSQL: ["mysql", "mysql2", "pymysql"],
        DatabaseType.MONGODB: ["mongodb", "mongoose", "pymongo"],
        DatabaseType.SQLITE: ["sqlite"],
        DatabaseType.REDIS: ["redis", "ioredis"],
    }

    AUTH_INDICATORS = {
        AuthType.JWT: ["jwt", "jsonwebtoken", "pyjwt", "jose"],
        AuthType.SESSION: ["session", "cookie-session", "express-session"],
        AuthType.OAUTH2: ["oauth", "passport", "auth0", "keycloak"],
        AuthType.BASIC: ["basic-auth", "http-basic"],
    }

    # ไดเรกทอรีที่ไม่ใช่โค้ดของโปรเจกต์เอง (vendor/build/vcs-internal) - ถ้าไม่
    # กรองออก ไฟล์ใน .git (blob ที่ไม่มีนามสกุล) หรือ node_modules/.venv จะ
    # ครอบงำผลลัพธ์ scan ทั้ง language detection และ route/component finding
    EXCLUDED_DIRS = {
        ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
        "dist", "build", ".pytest_cache", ".mypy_cache", ".tox",
    }

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        # Path(".").name == "" - scanning "the current directory" (the most
        # common invocation) must not produce a blank project name; resolve
        # to an absolute path first so .name reflects the real directory.
        resolved_name = self.project_path.resolve().name
        self.profile = ProjectProfile(
            name=resolved_name or str(self.project_path),
            framework="",
            language="",
            database="",
            api_style="",
            auth="",
            testing_tools=[],
            routes=[],
            api_endpoints=[],
            components=[],
            forms=[],
            dependencies={},
            has_tests=False,
        )

    def detect_stack(self) -> Dict[str, Any]:
        """ตรวจหา tech stack แบบเร็ว (ไม่สแกน routes/endpoints/components)"""
        self._detect_language()
        self._detect_framework()
        self._detect_database()
        self._detect_auth()
        self._detect_testing_tools()
        return {
            "language": self.profile.language,
            "framework": self.profile.framework,
            "database": self.profile.database,
            "auth": self.profile.auth,
            "testing_tools": self.profile.testing_tools,
        }

    def scan(self) -> ProjectProfile:
        """สแกน project ทั้งหมด"""
        self._detect_language()
        self._detect_framework()
        self._detect_database()
        self._detect_auth()
        self._detect_testing_tools()
        self._detect_dependencies()
        self._find_routes()
        self._find_api_endpoints()
        self._find_components()
        self._find_forms()
        self._check_existing_tests()
        self._detect_ci_cd()
        return self.profile

    def _walk(self, pattern: str = "*"):
        """rglob() ที่กรอง EXCLUDED_DIRS ออก - ใช้แทน self.project_path.rglob()
        ทุกที่ ไม่งั้น .git/node_modules/__pycache__ จะปนเข้าไปในผล scan
        (เจอจริง: .git blob ที่ไม่มีนามสกุลไฟล์ทำให้ language detection
        เข้าใจผิดว่าเป็น "Unknown" ในโปรเจกต์ Python ล้วน ๆ)
        """
        for p in self.project_path.rglob(pattern):
            if not any(part in self.EXCLUDED_DIRS for part in p.relative_to(self.project_path).parts):
                yield p

    def _detect_language(self):
        """ตรวจหาภาษาหลัก"""
        files = list(self._walk("*"))
        counts = {}
        for f in files:
            if f.is_file():
                ext = f.suffix
                counts[ext] = counts.get(ext, 0) + 1

        lang_map = {
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".py": "Python",
            ".java": "Java",
            ".go": "Go",
            ".rb": "Ruby",
            ".php": "PHP",
        }

        best = max(counts, key=counts.get) if counts else ""
        self.profile.language = lang_map.get(best, "Unknown")

    def _detect_framework(self):
        """ตรวจหา framework"""
        all_files = " ".join([str(p) for p in self._walk("*")])
        all_content = ""

        # อ่านไฟล์ config หลัก
        config_files = ["package.json", "requirements.txt", "pom.xml", "Gemfile", "composer.json"]
        for cf in config_files:
            path = self.project_path / cf
            if path.exists():
                try:
                    all_content += path.read_text(encoding="utf-8", errors="ignore")
                except:
                    pass

        for fw_type, indicators in self.FRAMEWORK_INDICATORS.items():
            for ind in indicators:
                if ind in all_content or ind in all_files:
                    self.profile.framework = fw_type.value
                    return

        self.profile.framework = FrameworkType.UNKNOWN.value

    def _detect_database(self):
        """ตรวจหา database"""
        all_content = ""
        for ext in [".env", ".env.local", "config.py", "settings.py", "docker-compose.yml"]:
            path = self.project_path / ext
            if path.exists():
                try:
                    all_content += path.read_text(encoding="utf-8", errors="ignore")
                except:
                    pass

        for db_type, indicators in self.DB_INDICATORS.items():
            for ind in indicators:
                if ind.lower() in all_content.lower():
                    self.profile.database = db_type.value
                    return

        self.profile.database = DatabaseType.UNKNOWN.value

    def _detect_auth(self):
        """ตรวจหา authentication mechanism"""
        all_content = ""
        for ext in [".env", "auth.py", "middleware.py", "security.py", "login.py"]:
            for path in self._walk(f"*{ext}"):
                try:
                    all_content += path.read_text(encoding="utf-8", errors="ignore")
                except:
                    pass

        for auth_type, indicators in self.AUTH_INDICATORS.items():
            for ind in indicators:
                if ind.lower() in all_content.lower():
                    self.profile.auth = auth_type.value
                    return

        self.profile.auth = AuthType.UNKNOWN.value

    def _detect_testing_tools(self):
        """ตรวจหา testing tools ที่มีอยู่"""
        tools = []
        package_json = self.project_path / "package.json"
        if package_json.exists():
            content = package_json.read_text(encoding="utf-8", errors="ignore")
            tool_map = {
                "playwright": "Playwright",
                "cypress": "Cypress",
                "jest": "Jest",
                "vitest": "Vitest",
                "mocha": "Mocha",
                "jasmine": "Jasmine",
                "@testing-library": "Testing Library",
            }
            for key, name in tool_map.items():
                if key in content:
                    tools.append(name)

        # Python
        for path in self._walk("pytest.ini"):
            tools.append("pytest")
        for path in self._walk("conftest.py"):
            tools.append("pytest")
        for path in self._walk("*robot*"):
            tools.append("Robot Framework")

        self.profile.testing_tools = list(set(tools))

    def _detect_dependencies(self):
        """อ่าน dependencies"""
        deps = {}
        package_json = self.project_path / "package.json"
        if package_json.exists():
            try:
                import json
                data = json.loads(package_json.read_text())
                deps.update(data.get("dependencies", {}))
                deps.update(data.get("devDependencies", {}))
            except:
                pass

        requirements = self.project_path / "requirements.txt"
        if requirements.exists():
            for line in requirements.read_text().splitlines():
                if "==" in line:
                    name, version = line.split("==", 1)
                    deps[name.strip()] = version.strip()

        self.profile.dependencies = deps

    def _find_routes(self):
        """หา routes จากโค้ด"""
        routes = []

        # Next.js / React Router
        for path in self._walk("*page.tsx"):
            rel = str(path.relative_to(self.project_path))
            route = rel.replace("page.tsx", "").replace("\\", "/")
            if route not in routes:
                routes.append(route)

        # Express / FastAPI routes
        for path in self._walk("*.py"):
            content = path.read_text(encoding="utf-8", errors="ignore")
            # FastAPI
            for match in re.finditer(r'@app\.(get|post|put|delete)\((["\'])([^"\']+)', content):
                r = match.group(3)
                if r not in routes:
                    routes.append(r)

        self.profile.routes = routes[:20]  # limit

    def _find_api_endpoints(self):
        """หา API endpoints"""
        endpoints = []
        for path in self._walk("*.py"):
            content = path.read_text(encoding="utf-8", errors="ignore")
            for match in re.finditer(r'@(app|router)\.(get|post|put|delete|patch)\((?:["\'])([^"\']+)', content):
                endpoints.append({
                    "method": match.group(2).upper(),
                    "path": match.group(3),
                    "file": str(path.relative_to(self.project_path)),
                })
        self.profile.api_endpoints = endpoints[:30]

    def _find_components(self):
        """หา UI components"""
        components = []
        for path in self._walk("*.tsx"):
            rel = str(path.relative_to(self.project_path))
            if "component" in rel.lower() or "ui" in rel.lower():
                components.append(rel)
        self.profile.components = components[:20]

    def _find_forms(self):
        """หา forms"""
        forms = []
        for path in self._walk("*.tsx"):
            content = path.read_text(encoding="utf-8", errors="ignore")
            if "<form" in content or "useForm" in content or "Form" in content:
                forms.append(str(path.relative_to(self.project_path)))
        self.profile.forms = forms[:10]

    def _check_existing_tests(self):
        """เช็คว่ามี tests อยู่แล้วหรือไม่"""
        test_dirs = ["tests", "__tests__", "test", "e2e", "cypress", "playwright"]
        for td in test_dirs:
            if (self.project_path / td).exists():
                self.profile.has_tests = True
                return
        self.profile.has_tests = False

    def _detect_ci_cd(self):
        """ตรวจหา CI/CD"""
        if (self.project_path / ".github" / "workflows").exists():
            self.profile.ci_cd = "GitHub Actions"
        elif (self.project_path / ".gitlab-ci.yml").exists():
            self.profile.ci_cd = "GitLab CI"
        elif (self.project_path / "Jenkinsfile").exists():
            self.profile.ci_cd = "Jenkins"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self.profile)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# Convenience functions
async def project_scan(project_path: str) -> Dict[str, Any]:
    """MCP tool: project.scan"""
    scanner = ProjectScanner(project_path)
    profile = scanner.scan()
    return scanner.to_dict()


def project_structure(project_path: str) -> str:
    """MCP tool: project.structure - แสดง tree"""
    lines = []
    for root, dirs, files in os.walk(project_path):
        level = root.replace(project_path, "").count(os.sep)
        indent = " " * 2 * level
        lines.append(f"{indent}{os.path.basename(root)}/")
        sub_indent = " " * 2 * (level + 1)
        for f in files[:10]:  # limit
            lines.append(f"{sub_indent}{f}")
        if len(files) > 10:
            lines.append(f"{sub_indent}... ({len(files) - 10} more)")
    return "\n".join(lines)
