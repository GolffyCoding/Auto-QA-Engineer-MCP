"""
Phase 3: Automation Engine - Mobile Adapter
รองรับ Appium, Maestro
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Any
import asyncio
import os
import tempfile
import yaml


class MobileAdapter(ABC):
    """Abstract base สำหรับ mobile automation"""

    @abstractmethod
    async def launch(self, app_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def tap(self, selector: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def swipe(self, direction: str, distance: int = 300) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def type_text(self, selector: str, text: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def assert_element(self, selector: str) -> bool:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass


class AppiumAdapter(MobileAdapter):
    """Appium implementation - ต่อ Appium server จริงผ่าน Appium-Python-Client

    ต้องมี Appium server รันอยู่ (`appium` ที่ port ที่กำหนด, default
    http://127.0.0.1:4723) และมี device/emulator จริงต่ออยู่ (`adb devices`
    ต้องเห็น device) ไม่งั้นจะ error ตรง ๆ ตอน `launch()` (ไม่ใช่ silent
    success แบบ stub เดิม)
    """

    def __init__(
        self,
        server_url: str = "http://127.0.0.1:4723",
        platform_name: str = "Android",
        automation_name: str = "UiAutomator2",
        device_name: Optional[str] = None,
        app_activity: Optional[str] = None,
        capabilities: Optional[Dict[str, Any]] = None,
    ):
        self.server_url = server_url
        self.platform_name = platform_name
        self.automation_name = automation_name
        self.device_name = device_name
        # ".MainActivity" เป็นแค่ default ที่ใช้ได้กับแอปส่วนน้อยเท่านั้น - แอป
        # จริงส่วนใหญ่ (รวมถึงระบบแอปอย่าง Settings) ใช้ชื่อ activity อื่น
        # ต้องมีทางกำหนดเองได้ ไม่งั้น launch() จะ fail กับแอปส่วนใหญ่ในโลกจริง
        self.app_activity = app_activity
        # capability เพิ่มเติมที่จำเป็นจริงบนอุปกรณ์บางรุ่น/บาง OEM (เช่น
        # ColorOS/OPPO/Realme ที่ block WRITE_SECURE_SETTINGS หรือ block
        # `pm clear` บนแอประบบ) - ทดสอบจริงกับ CPH1819 (Android 10) เจอว่า
        # ต้องใช้ทั้ง appium:ignoreHiddenApiPolicyError และ appium:noReset
        # ถึงจะสร้าง session ผ่าน ไม่งั้น session ตายตั้งแต่ createSession
        self.capabilities = capabilities or {}
        self._driver = None

    def _build_options(self, app_id: str):
        if self.platform_name.lower() == "android":
            from appium.options.android import UiAutomator2Options
            options = UiAutomator2Options()
            options.app_package = app_id
            options.app_activity = self.app_activity or ".MainActivity"
        else:
            from appium.options.ios import XCUITestOptions
            options = XCUITestOptions()
            options.bundle_id = app_id

        options.automation_name = self.automation_name
        options.platform_name = self.platform_name
        if self.device_name:
            options.device_name = self.device_name
        for key, value in self.capabilities.items():
            options.set_capability(key, value)
        return options

    async def launch(self, app_id: str) -> Dict[str, Any]:
        from appium import webdriver

        options = self._build_options(app_id)
        loop = asyncio.get_event_loop()
        self._driver = await loop.run_in_executor(
            None, lambda: webdriver.Remote(command_executor=self.server_url, options=options)
        )
        return {"success": True, "app": app_id, "session_id": self._driver.session_id}

    def _find(self, selector: str):
        from appium.webdriver.common.appiumby import AppiumBy
        by = AppiumBy.XPATH if selector.startswith("//") else AppiumBy.ACCESSIBILITY_ID
        return self._driver.find_element(by, selector)

    async def tap(self, selector: str) -> Dict[str, Any]:
        if self._driver is None:
            raise RuntimeError("Appium session not started - call launch() first")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._find(selector).click())
        return {"success": True, "action": "tap", "selector": selector}

    async def swipe(self, direction: str, distance: int = 300) -> Dict[str, Any]:
        if self._driver is None:
            raise RuntimeError("Appium session not started - call launch() first")
        size = self._driver.get_window_size()
        cx, cy = size["width"] // 2, size["height"] // 2
        offsets = {
            "up": (0, -distance),
            "down": (0, distance),
            "left": (-distance, 0),
            "right": (distance, 0),
        }
        dx, dy = offsets.get(direction.lower(), (0, -distance))
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._driver.execute_script(
                "mobile: swipeGesture",
                {
                    "left": max(cx - abs(dx), 0), "top": max(cy - abs(dy), 0),
                    "width": min(abs(dx) * 2, size["width"]) or size["width"],
                    "height": min(abs(dy) * 2, size["height"]) or size["height"],
                    "direction": direction.lower(),
                    "percent": 0.75,
                },
            ),
        )
        return {"success": True, "action": "swipe", "direction": direction}

    async def type_text(self, selector: str, text: str) -> Dict[str, Any]:
        if self._driver is None:
            raise RuntimeError("Appium session not started - call launch() first")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._find(selector).send_keys(text))
        return {"success": True, "action": "type", "selector": selector, "text": text}

    async def assert_element(self, selector: str) -> bool:
        if self._driver is None:
            raise RuntimeError("Appium session not started - call launch() first")
        loop = asyncio.get_event_loop()
        try:
            elem = await loop.run_in_executor(None, lambda: self._find(selector))
            return await loop.run_in_executor(None, lambda: elem.is_displayed())
        except Exception:
            return False

    async def close(self) -> None:
        if self._driver:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._driver.quit)
            self._driver = None


class MaestroAdapter(MobileAdapter):
    """Maestro implementation - รัน `maestro test` จริงกับ flow YAML ที่ generate เอง

    เหมือน CypressAdapter: Maestro ไม่มี interactive session ข้าม process
    เลย ต้อง replay flow ทั้งหมดของ session นี้เป็นไฟล์ YAML เดียวแล้วรันใหม่
    ทุกครั้งที่มี action ใหม่ ต้องมี Maestro CLI ติดตั้ง (`maestro` ใน PATH)
    และมี device/emulator จริงต่ออยู่ ไม่งั้น `maestro test` จะ fail ตรง ๆ
    """

    def __init__(self, udid: Optional[str] = None, maestro_bin: str = "maestro"):
        self.udid = udid
        self._maestro_bin = maestro_bin
        self._app_id: Optional[str] = None
        self._steps: List[Dict[str, Any]] = []
        self._workdir = Path(tempfile.mkdtemp(prefix="qa-mcp-maestro-"))

    # ข้อความ error ที่ Maestro CLI คืนมาเป็นครั้งคราวกับอุปกรณ์จริงที่ต่อผ่าน USB
    # (พิสูจน์แล้วว่า transient จริง - ทดสอบยิง `maestro test` เดิมซ้ำ 3 ครั้งติดกัน
    # กับอุปกรณ์จริง ได้ COMPLETED 2 ครั้ง, "not connected" 1 ครั้ง แม้ `adb devices`
    # จะเห็น device ต่ออยู่ตลอดเวลา) - MaestroAdapter เสี่ยงกับปัญหานี้มากกว่า
    # AppiumAdapter เพราะ spawn `maestro test` process ใหม่ทุก action แทนที่จะ
    # ถือ session เดียวยาว ๆ จึงคุ้มที่จะ retry เฉพาะ error นี้แบบสั้น ๆ
    _TRANSIENT_DISCONNECT_MARKER = "was requested, but it is not connected"
    _MAX_RETRIES = 2

    async def _run_flow(self) -> Dict[str, Any]:
        flow_path = self._workdir / "flow.yaml"
        # Maestro's YAML format is `appId: ...` then a `---` document separator
        # then a plain list of steps - not one dict, so build the text by hand.
        lines = [f"appId: {self._app_id or 'unknown'}", "---"]
        for step in self._steps:
            lines.append("- " + yaml.safe_dump(step, default_flow_style=True).strip())
        flow_path.write_text("\n".join(lines) + "\n")

        args = [self._maestro_bin, "test", str(flow_path), "--format", "junit",
                 "--output", str(self._workdir / "report.xml")]
        if self.udid:
            args += ["--udid", self.udid]

        for attempt in range(self._MAX_RETRIES + 1):
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "MAESTRO_CLI_NO_ANALYTICS": "1"},
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            output = stdout.decode(errors="ignore")
            if proc.returncode != 0 and self._TRANSIENT_DISCONNECT_MARKER in output and attempt < self._MAX_RETRIES:
                await asyncio.sleep(1)
                continue
            break

        return {
            "exit_code": proc.returncode,
            "passed": proc.returncode == 0,
            "output_tail": stdout.decode(errors="ignore")[-1500:],
        }

    async def launch(self, app_id: str) -> Dict[str, Any]:
        self._app_id = app_id
        self._steps.append({"launchApp": app_id})
        result = await self._run_flow()
        return {"success": result["passed"], "app": app_id, "detail": result}

    async def tap(self, selector: str) -> Dict[str, Any]:
        self._steps.append({"tapOn": selector})
        result = await self._run_flow()
        return {"success": result["passed"], "action": "tap", "selector": selector, "detail": result}

    async def swipe(self, direction: str, distance: int = 300) -> Dict[str, Any]:
        self._steps.append({"swipe": {"direction": direction.upper()}})
        result = await self._run_flow()
        return {"success": result["passed"], "action": "swipe", "direction": direction, "detail": result}

    async def type_text(self, selector: str, text: str) -> Dict[str, Any]:
        self._steps.append({"tapOn": selector})
        self._steps.append({"inputText": text})
        result = await self._run_flow()
        return {"success": result["passed"], "action": "type", "selector": selector, "text": text, "detail": result}

    async def assert_element(self, selector: str) -> bool:
        self._steps.append({"assertVisible": selector})
        result = await self._run_flow()
        return result["passed"]

    async def close(self) -> None:
        self._app_id = None
        self._steps = []


class MobileFactory:
    """Factory สร้าง mobile adapter ตาม framework พร้อม cache เป็น singleton ต่อ framework
    (เหมือน BrowserFactory) เพื่อให้ mobile.launch -> mobile.tap ใช้ session เดียวกัน
    """

    _instances: Dict[str, MobileAdapter] = {}

    @classmethod
    def create(cls, framework: str = "appium", **kwargs) -> MobileAdapter:
        framework = framework.lower()
        if framework in cls._instances:
            return cls._instances[framework]

        if framework == "appium":
            adapter: MobileAdapter = AppiumAdapter(**kwargs)
        elif framework == "maestro":
            adapter = MaestroAdapter(**kwargs)
        else:
            raise ValueError(f"Unsupported mobile framework: {framework}")

        cls._instances[framework] = adapter
        return adapter

    @classmethod
    async def close(cls, framework: str = "appium") -> bool:
        framework = framework.lower()
        adapter = cls._instances.pop(framework, None)
        if adapter is None:
            return False
        await adapter.close()
        return True


# MCP Tools
async def mobile_launch(app_id: str, framework: str = "appium") -> Dict[str, Any]:
    """MCP tool: mobile.launch"""
    adapter = MobileFactory.create(framework)
    return await adapter.launch(app_id)


async def mobile_tap(selector: str, framework: str = "appium") -> Dict[str, Any]:
    """MCP tool: mobile.tap"""
    adapter = MobileFactory.create(framework)
    return await adapter.tap(selector)


async def mobile_swipe(direction: str, distance: int = 300, framework: str = "appium") -> Dict[str, Any]:
    """MCP tool: mobile.swipe"""
    adapter = MobileFactory.create(framework)
    return await adapter.swipe(direction, distance)


async def mobile_type_text(selector: str, text: str, framework: str = "appium") -> Dict[str, Any]:
    """MCP tool: mobile.type_text"""
    adapter = MobileFactory.create(framework)
    return await adapter.type_text(selector, text)


async def mobile_assert_element(selector: str, framework: str = "appium") -> Dict[str, Any]:
    """MCP tool: mobile.assert_element"""
    adapter = MobileFactory.create(framework)
    visible = await adapter.assert_element(selector)
    return {"selector": selector, "visible": visible}


async def mobile_close(framework: str = "appium") -> Dict[str, Any]:
    """MCP tool: mobile.close"""
    closed = await MobileFactory.close(framework)
    return {"framework": framework, "closed": closed}
