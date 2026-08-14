"""
Core: FailureDiagnostician
วิเคราะห์ failure ระดับสูง
"""
from typing import Dict, List, Optional, Any


class FailureDiagnostician:
    """Diagnostician ระดับสูง - ประสานงานกับ FailureAnalyzer"""

    def diagnose(self, test_result: Dict[str, Any]) -> Dict[str, Any]:
        """วิเคราะห์ failure จาก test result"""
        from qa_mcp.failure_analysis.analyzer import FailureAnalyzer, FailureEvidence

        evidence = FailureEvidence(
            failure_id=test_result.get("test_id", "unknown"),
            test_name=test_result.get("test_name", ""),
            expected="Expected test to pass",
            actual=test_result.get("error_message", test_result.get("stderr", "Unknown error")),
            console_log=test_result.get("stderr", ""),
            timestamp=test_result.get("end_time", ""),
        )

        analyzer = FailureAnalyzer()
        diagnosis = analyzer.inspect(evidence)

        return {
            "test_id": test_result.get("test_id"),
            "diagnosis": diagnosis.to_dict(),
            "recommendation": diagnosis.suggested_fix,
            "severity": "critical" if diagnosis.confidence > 80 else "high",
        }

    def batch_diagnose(self, test_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """วิเคราะห์หลาย test results พร้อมกัน"""
        return [self.diagnose(r) for r in test_results if r.get("status") != "passed"]
