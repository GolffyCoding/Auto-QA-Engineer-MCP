"""
Analyzer: Log Analysis
วิเคราะห์ logs เพื่อหา patterns และ errors
"""
import re
from typing import Dict, List, Optional, Any


class LogAnalyzer:
    """วิเคราะห์ log files"""

    ERROR_PATTERNS = [
        r"ERROR",
        r"Exception",
        r"Traceback",
        r"FATAL",
        r"CRITICAL",
        r"failed",
        r"timeout",
        r"connection refused",
    ]

    def analyze(self, log_content: str) -> Dict[str, Any]:
        """วิเคราะห์ log content"""
        lines = log_content.splitlines()
        errors = []
        warnings = []

        for i, line in enumerate(lines):
            for pattern in self.ERROR_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    errors.append({
                        "line": i + 1,
                        "text": line.strip(),
                        "pattern": pattern,
                    })
            if "WARNING" in line:
                warnings.append({"line": i + 1, "text": line.strip()})

        return {
            "total_lines": len(lines),
            "errors_found": len(errors),
            "warnings_found": len(warnings),
            "errors": errors[:20],
            "warnings": warnings[:10],
        }

    def find_stack_traces(self, log_content: str) -> List[str]:
        """หา stack traces จาก logs"""
        traces = []
        lines = log_content.splitlines()
        in_trace = False
        current_trace = []

        for line in lines:
            if "Traceback" in line:
                in_trace = True
                current_trace = [line]
            elif in_trace:
                if line.strip() and not line.startswith(" ") and not line.startswith("\t"):
                    in_trace = False
                    traces.append("\n".join(current_trace))
                    current_trace = []
                else:
                    current_trace.append(line)

        if current_trace:
            traces.append("\n".join(current_trace))

        return traces
