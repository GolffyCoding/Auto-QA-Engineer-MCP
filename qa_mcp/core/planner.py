"""
Core: TestPlanner
วางแผนการทดสอบจาก project intelligence
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class TestPlan:
    """แผนการทดสอบ"""
    plan_id: str
    project_name: str
    features: List[str]
    test_types: List[str]
    estimated_duration_min: int
    priority_order: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "project_name": self.project_name,
            "features": self.features,
            "test_types": self.test_types,
            "estimated_duration_min": self.estimated_duration_min,
            "priority_order": self.priority_order,
        }


class TestPlanner:
    """วางแผนการทดสอบ"""

    def plan(self, project_profile: Dict[str, Any]) -> TestPlan:
        """สร้าง test plan จาก project profile"""
        features = []

        # สร้าง features จาก routes
        for route in project_profile.get("routes", []):
            features.append(f"Route: {route}")

        # สร้าง features จาก API endpoints
        for ep in project_profile.get("api_endpoints", [])[:5]:
            features.append(f"API {ep['method']} {ep['path']}")

        # สร้าง features จาก forms
        for form in project_profile.get("forms", []):
            features.append(f"Form: {form}")

        test_types = ["smoke", "e2e", "api", "regression"]
        if project_profile.get("auth"):
            test_types.append("security")

        return TestPlan(
            plan_id=f"plan-{project_profile['name']}",
            project_name=project_profile["name"],
            features=features,
            test_types=test_types,
            estimated_duration_min=len(features) * 5,
            priority_order=["smoke", "critical paths", "e2e", "api", "regression"],
        )
