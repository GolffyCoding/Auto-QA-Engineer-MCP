"""
MCP Server - Main entry point
รวมทุก tools ไว้ที่นี่เพื่อให้ LLM เรียกใช้
"""
import asyncio
import inspect
import json
from typing import Dict, List, Optional, Any
from datetime import datetime


class QAMCPServer:
    """QA MCP Server - รวมทุก tools"""

    def __init__(self):
        self.tools = self._register_tools()

    def _register_tools(self) -> Dict[str, Any]:
        """ลงทะเบียนทุก tools"""
        return {
            # Phase 1: Project Intelligence
            "project.scan": "qa_mcp.project_intelligence.scanner.project_scan",
            "project.structure": "qa_mcp.project_intelligence.scanner.project_structure",
            "project.detect_stack": "qa_mcp.project_intelligence.scanner.ProjectScanner.detect_stack",

            # Phase 2: Test Design
            "test.generate": "qa_mcp.test_design.generator.test_generate",
            "test.generate_e2e": "qa_mcp.test_design.generator.test_generate",
            "test.generate_api": "qa_mcp.test_design.generator.test_generate",
            "test.analyze_coverage": "qa_mcp.test_design.generator.test_analyze_coverage",
            "test.prioritize": "qa_mcp.test_design.generator.TestDesigner.prioritize",

            # Phase 3: Automation Engine
            "browser.open": "qa_mcp.adapters.browser.browser_open",
            "browser.click": "qa_mcp.adapters.browser.browser_click",
            "browser.fill": "qa_mcp.adapters.browser.browser_fill",
            "browser.screenshot": "qa_mcp.adapters.browser.browser_screenshot",
            "browser.assert": "qa_mcp.adapters.browser.browser_assert",
            "browser.close": "qa_mcp.adapters.browser.browser_close",
            "api.request": "qa_mcp.adapters.api.api_request",
            "api.assert_status": "qa_mcp.adapters.api.api_assert_status",
            "api.load_test": "qa_mcp.adapters.api.api_load_test",
            "mobile.launch": "qa_mcp.adapters.mobile.mobile_launch",
            "mobile.tap": "qa_mcp.adapters.mobile.mobile_tap",
            "mobile.swipe": "qa_mcp.adapters.mobile.mobile_swipe",
            "mobile.type_text": "qa_mcp.adapters.mobile.mobile_type_text",
            "mobile.assert_element": "qa_mcp.adapters.mobile.mobile_assert_element",
            "mobile.close": "qa_mcp.adapters.mobile.mobile_close",

            # Phase 4: Execution
            "test.create": "qa_mcp.execution.executor.test_create",
            "test.create_run": "qa_mcp.execution.executor.test_create_run",
            "test.run": "qa_mcp.execution.executor.test_run",
            "test.run_single": "qa_mcp.execution.executor.TestExecutor.run_single",
            "test.rerun": "qa_mcp.execution.executor.test_rerun",
            "test.get_run": "qa_mcp.execution.executor.test_get_run",
            "environment.start": "qa_mcp.execution.executor.environment_start",
            "environment.stop": "qa_mcp.execution.executor.environment_stop",

            # Phase 5: Failure Analysis
            "failure.inspect": "qa_mcp.failure_analysis.analyzer.failure_inspect",
            "failure.classify": "qa_mcp.failure_analysis.analyzer.failure_classify",
            "failure.find_root_cause": "qa_mcp.failure_analysis.analyzer.failure_find_root_cause",
            "failure.get_evidence": "qa_mcp.failure_analysis.analyzer.failure_get_evidence",
            "failure.compare_runs": "qa_mcp.failure_analysis.analyzer.failure_compare_runs",

            # Phase 6: Fix Loop
            "fix_loop.diagnose": "qa_mcp.fix_loop.engine.fix_loop_diagnose",
            "fix_loop.propose": "qa_mcp.fix_loop.engine.fix_loop_propose",
            "fix_loop.approve": "qa_mcp.fix_loop.engine.fix_loop_approve",
            "fix_loop.apply_patch": "qa_mcp.fix_loop.engine.fix_loop_apply_patch",
            "fix_loop.verify": "qa_mcp.fix_loop.engine.fix_loop_verify",

            # Phase 7: Defect / CI/CD
            "defect.create": "qa_mcp.defect_cicd.defect_manager.defect_create",
            "defect.attach_evidence": "qa_mcp.defect_cicd.defect_manager.defect_attach_evidence",
            "git.status": "qa_mcp.defect_cicd.defect_manager.git_status",
            "git.diff": "qa_mcp.defect_cicd.defect_manager.git_diff",
            "git.create_branch": "qa_mcp.defect_cicd.defect_manager.git_create_branch",
            "git.commit": "qa_mcp.defect_cicd.defect_manager.git_commit",
            "ci.detect": "qa_mcp.defect_cicd.defect_manager.ci_detect",
            "ci.run": "qa_mcp.defect_cicd.defect_manager.ci_run",
            "ci.get_status": "qa_mcp.defect_cicd.defect_manager.ci_get_status",

            # Phase 8: Reporting
            "report.generate": "qa_mcp.core.reporter.report_generate",
            "report.generate_html": "qa_mcp.core.reporter.report_generate_html",
            "report.generate_pdf": "qa_mcp.core.reporter.report_generate_pdf",

            # Phase 9: Database Validation
            "db.get_table_state": "qa_mcp.analyzers.database_analyzer.db_get_table_state",
            "db.check_fk_integrity": "qa_mcp.analyzers.database_analyzer.db_check_fk_integrity",
            "db.query": "qa_mcp.analyzers.database_analyzer.db_query",
        }

    async def call(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """เรียก tool ตามชื่อ"""
        tool_path = self.tools.get(tool_name)
        if not tool_path:
            return {"error": f"Tool '{tool_name}' not found"}

        # Dynamic import and call
        parts = tool_path.split(".")
        module_path = ".".join(parts[:-1])
        func_name = parts[-1]

        try:
            try:
                module = __import__(module_path, fromlist=[func_name])
                target = getattr(module, func_name)
            except ModuleNotFoundError:
                # tool_path points at "module.ClassName.method" instead of a
                # plain function - import the class, instantiate it (using
                # any kwargs that match its constructor), then bind the method.
                class_module_path = ".".join(parts[:-2])
                class_name = parts[-2]
                method_name = parts[-1]
                module = __import__(class_module_path, fromlist=[class_name])
                cls = getattr(module, class_name)

                if isinstance(inspect.getattr_static(cls, method_name), staticmethod):
                    target = getattr(cls, method_name)
                else:
                    ctor_params = [
                        name for name in inspect.signature(cls.__init__).parameters
                        if name != "self"
                    ]
                    ctor_kwargs = {k: kwargs.pop(k) for k in ctor_params if k in kwargs}
                    instance = cls(**ctor_kwargs)
                    target = getattr(instance, method_name)

            if asyncio.iscoroutinefunction(target):
                result = await target(**kwargs)
            else:
                result = target(**kwargs)

            # Tools that return a dataclass instance (e.g. TestResult) instead
            # of a plain dict need converting so the CLI/MCP layer can serialize it.
            return result.to_dict() if hasattr(result, "to_dict") else result
        except Exception as e:
            return {"error": str(e), "tool": tool_name}

    def list_tools(self) -> List[Dict[str, Any]]:
        """แสดงรายการทุก tools"""
        return [
            {"name": name, "path": path}
            for name, path in self.tools.items()
        ]


def main():
    """CLI entry point"""
    import argparse
    parser = argparse.ArgumentParser(description="QA MCP Server")
    parser.add_argument("--list-tools", action="store_true", help="List all available tools")
    parser.add_argument("--call", type=str, help="Call a tool by name")
    parser.add_argument("--args", type=str, default="{}", help="JSON arguments for the tool")
    args = parser.parse_args()

    server = QAMCPServer()

    if args.list_tools:
        tools = server.list_tools()
        print(json.dumps(tools, indent=2))
    elif args.call:
        kwargs = json.loads(args.args)
        result = asyncio.run(server.call(args.call, **kwargs))
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
