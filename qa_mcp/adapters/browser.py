"""
Phase 3: Automation Engine - Browser Adapter
Abstraction layer สำหรับ browser automation
รองรับ Playwright, Selenium, Cypress, Robot
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import json
import os
import shutil


class BrowserType(Enum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


@dataclass
class ScreenshotEvidence:
    path: str
    timestamp: str
    description: str


@dataclass
class BrowserAction:
    action: str  # open, click, fill, select, screenshot, assert, wait
    target: Optional[str] = None  # selector หรือ URL
    value: Optional[str] = None
    timeout: int = 30000
    options: Dict[str, Any] = field(default_factory=dict)


class BrowserAdapter(ABC):
    """Abstract base สำหรับทุก browser automation framework"""

    @abstractmethod
    async def open(self, url: str, options: Optional[Dict] = None) -> Dict[str, Any]:
        """เปิดหน้าเว็บ"""
        pass

    @abstractmethod
    async def click(self, selector: str, options: Optional[Dict] = None) -> Dict[str, Any]:
        """คลิก element"""
        pass

    @abstractmethod
    async def fill(self, selector: str, value: str) -> Dict[str, Any]:
        """กรอกข้อมูล"""
        pass

    @abstractmethod
    async def select(self, selector: str, value: str) -> Dict[str, Any]:
        """เลือก dropdown"""
        pass

    @abstractmethod
    async def get_text(self, selector: str) -> str:
        """อ่านข้อความ"""
        pass

    @abstractmethod
    async def screenshot(self, name: str, description: str = "") -> ScreenshotEvidence:
        """ถ่าย screenshot"""
        pass

    @abstractmethod
    async def wait(self, condition: str, timeout: int = 30000) -> bool:
        """รอ condition"""
        pass

    @abstractmethod
    async def assert_visible(self, selector: str) -> bool:
        """ตรวจสอบ element แสดงผล"""
        pass

    @abstractmethod
    async def assert_text(self, selector: str, expected: str) -> bool:
        """ตรวจสอบข้อความ"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """ปิด browser"""
        pass

    @abstractmethod
    async def get_console_logs(self) -> List[Dict[str, Any]]:
        """ดึง console logs"""
        pass

    @abstractmethod
    async def get_network_logs(self) -> List[Dict[str, Any]]:
        """ดึง network requests"""
        pass


class PlaywrightAdapter(BrowserAdapter):
    """Playwright implementation"""

    def __init__(self, browser_type: BrowserType = BrowserType.CHROMIUM, headless: bool = True):
        self.browser_type = browser_type
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._console_logs: List[Dict] = []
        self._network_logs: List[Dict] = []

    async def _ensure_started(self):
        if self._playwright is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            browser_cls = getattr(self._playwright, self.browser_type.value)
            self._browser = await browser_cls.launch(headless=self.headless)
            self._context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                record_video_dir="./videos/" if not self.headless else None,
            )
            self._page = await self._context.new_page()

            # Capture console logs
            self._page.on("console", lambda msg: self._console_logs.append({
                "type": msg.type,
                "text": msg.text,
                "location": str(msg.location),
            }))

            # Capture network
            self._page.on("request", lambda req: self._network_logs.append({
                "method": req.method,
                "url": req.url,
                "type": "request",
            }))
            self._page.on("response", lambda res: self._network_logs.append({
                "status": res.status,
                "url": res.url,
                "type": "response",
            }))

    async def open(self, url: str, options: Optional[Dict] = None) -> Dict[str, Any]:
        await self._ensure_started()
        response = await self._page.goto(url, wait_until="networkidle")
        return {
            "status": response.status if response else None,
            "url": self._page.url,
            "title": await self._page.title(),
        }

    async def click(self, selector: str, options: Optional[Dict] = None) -> Dict[str, Any]:
        await self._ensure_started()
        await self._page.click(selector)
        return {"success": True, "selector": selector}

    async def fill(self, selector: str, value: str) -> Dict[str, Any]:
        await self._ensure_started()
        await self._page.fill(selector, value)
        return {"success": True, "selector": selector, "value": value}

    async def select(self, selector: str, value: str) -> Dict[str, Any]:
        await self._ensure_started()
        await self._page.select_option(selector, value)
        return {"success": True, "selector": selector, "value": value}

    async def get_text(self, selector: str) -> str:
        await self._ensure_started()
        return await self._page.inner_text(selector)

    async def screenshot(self, name: str, description: str = "") -> ScreenshotEvidence:
        await self._ensure_started()
        from datetime import datetime
        timestamp = datetime.now().isoformat()
        safe_timestamp = timestamp.replace(":", "-")
        path = f"./screenshots/{name}_{safe_timestamp}.png"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        await self._page.screenshot(path=path, full_page=True)
        return ScreenshotEvidence(path=path, timestamp=timestamp, description=description)

    async def wait(self, condition: str, timeout: int = 30000) -> bool:
        await self._ensure_started()
        try:
            await self._page.wait_for_selector(condition, timeout=timeout)
            return True
        except:
            return False

    async def assert_visible(self, selector: str) -> bool:
        await self._ensure_started()
        try:
            await self._page.wait_for_selector(selector, state="visible", timeout=5000)
            return True
        except:
            return False

    async def assert_text(self, selector: str, expected: str) -> bool:
        await self._ensure_started()
        actual = await self.get_text(selector)
        return expected in actual

    async def close(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def get_console_logs(self) -> List[Dict[str, Any]]:
        return self._console_logs.copy()

    async def get_network_logs(self) -> List[Dict[str, Any]]:
        return self._network_logs.copy()


class SeleniumAdapter(BrowserAdapter):
    """Selenium implementation (stub - เตรียมไว้สำหรับเชื่อมต่อจริง)"""

    def __init__(self, browser_type: BrowserType = BrowserType.CHROMIUM, headless: bool = True):
        self.browser_type = browser_type
        self.headless = headless
        self._driver = None
        self._console_logs: List[Dict] = []
        self._network_logs: List[Dict] = []

    async def _ensure_started(self):
        if self._driver is None:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            options = Options()
            if self.headless:
                options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            self._driver = webdriver.Chrome(options=options)
            self._driver.set_window_size(1920, 1080)

    async def open(self, url: str, options: Optional[Dict] = None) -> Dict[str, Any]:
        await self._ensure_started()
        self._driver.get(url)
        return {
            "status": 200,
            "url": self._driver.current_url,
            "title": self._driver.title,
        }

    async def click(self, selector: str, options: Optional[Dict] = None) -> Dict[str, Any]:
        await self._ensure_started()
        from selenium.webdriver.common.by import By
        # รองรับทั้ง CSS selector และ XPath
        by = By.CSS_SELECTOR if not selector.startswith("//") else By.XPATH
        self._driver.find_element(by, selector).click()
        return {"success": True, "selector": selector}

    async def fill(self, selector: str, value: str) -> Dict[str, Any]:
        await self._ensure_started()
        from selenium.webdriver.common.by import By
        by = By.CSS_SELECTOR if not selector.startswith("//") else By.XPATH
        elem = self._driver.find_element(by, selector)
        elem.clear()
        elem.send_keys(value)
        return {"success": True, "selector": selector, "value": value}

    async def select(self, selector: str, value: str) -> Dict[str, Any]:
        await self._ensure_started()
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import Select
        by = By.CSS_SELECTOR if not selector.startswith("//") else By.XPATH
        elem = self._driver.find_element(by, selector)
        Select(elem).select_by_visible_text(value)
        return {"success": True, "selector": selector, "value": value}

    async def get_text(self, selector: str) -> str:
        await self._ensure_started()
        from selenium.webdriver.common.by import By
        by = By.CSS_SELECTOR if not selector.startswith("//") else By.XPATH
        return self._driver.find_element(by, selector).text

    async def screenshot(self, name: str, description: str = "") -> ScreenshotEvidence:
        await self._ensure_started()
        from datetime import datetime
        timestamp = datetime.now().isoformat()
        safe_timestamp = timestamp.replace(":", "-")
        path = f"./screenshots/{name}_{safe_timestamp}.png"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._driver.save_screenshot(path)
        return ScreenshotEvidence(path=path, timestamp=timestamp, description=description)

    async def wait(self, condition: str, timeout: int = 30000) -> bool:
        await self._ensure_started()
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        by = By.CSS_SELECTOR if not condition.startswith("//") else By.XPATH
        try:
            WebDriverWait(self._driver, timeout / 1000).until(
                EC.presence_of_element_located((by, condition))
            )
            return True
        except:
            return False

    async def assert_visible(self, selector: str) -> bool:
        await self._ensure_started()
        from selenium.webdriver.common.by import By
        by = By.CSS_SELECTOR if not selector.startswith("//") else By.XPATH
        try:
            return self._driver.find_element(by, selector).is_displayed()
        except:
            return False

    async def assert_text(self, selector: str, expected: str) -> bool:
        actual = await self.get_text(selector)
        return expected in actual

    async def close(self) -> None:
        if self._driver:
            self._driver.quit()

    async def get_console_logs(self) -> List[Dict[str, Any]]:
        return self._console_logs.copy()

    async def get_network_logs(self) -> List[Dict[str, Any]]:
        return self._network_logs.copy()


class RobotFrameworkAdapter(BrowserAdapter):
    """Robot Framework implementation - ใช้ SeleniumLibrary จริง (ไม่ใช่ stub)

    รันผ่าน API ของ `SeleniumLibrary` โดยตรง (ไม่ต้องเขียนไฟล์ .robot) เพราะ
    keyword ของ SeleniumLibrary ก็คือ method ของคลาสนี้อยู่แล้ว - นี่คือ
    วิธีที่ real automation code เรียกใช้ Robot Framework library แบบ
    programmatic โดยไม่ต้องพึ่ง `robot` test runner
    """

    def __init__(self, browser_type: BrowserType = BrowserType.CHROMIUM, headless: bool = True):
        self.browser_type = browser_type
        self.headless = headless
        self._lib = None
        self._console_logs: List[Dict] = []
        self._network_logs: List[Dict] = []

    @staticmethod
    def _locator(selector: str) -> str:
        """แปลง CSS/XPath selector ให้เป็น locator syntax ของ SeleniumLibrary"""
        if selector.startswith("//"):
            return f"xpath:{selector}"
        return f"css:{selector}"

    async def _ensure_started(self):
        if self._lib is None:
            import SeleniumLibrary
            from selenium.webdriver.chrome.options import Options

            self._lib = SeleniumLibrary.SeleniumLibrary()
            options = Options()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            self._lib.open_browser("about:blank", browser="chrome", options=options)

    async def open(self, url: str, options: Optional[Dict] = None) -> Dict[str, Any]:
        await self._ensure_started()
        self._lib.go_to(url)
        return {
            "status": 200,
            "url": self._lib.get_location(),
            "title": self._lib.get_title(),
        }

    async def click(self, selector: str, options: Optional[Dict] = None) -> Dict[str, Any]:
        await self._ensure_started()
        self._lib.click_element(self._locator(selector))
        return {"success": True, "selector": selector}

    async def fill(self, selector: str, value: str) -> Dict[str, Any]:
        await self._ensure_started()
        self._lib.input_text(self._locator(selector), value)
        return {"success": True, "selector": selector, "value": value}

    async def select(self, selector: str, value: str) -> Dict[str, Any]:
        await self._ensure_started()
        self._lib.select_from_list_by_label(self._locator(selector), value)
        return {"success": True, "selector": selector, "value": value}

    async def get_text(self, selector: str) -> str:
        await self._ensure_started()
        return self._lib.get_text(self._locator(selector))

    async def screenshot(self, name: str, description: str = "") -> ScreenshotEvidence:
        await self._ensure_started()
        from datetime import datetime
        timestamp = datetime.now().isoformat()
        safe_timestamp = timestamp.replace(":", "-")
        path = f"./screenshots/{name}_{safe_timestamp}.png"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._lib.capture_page_screenshot(filename=path)
        return ScreenshotEvidence(path=path, timestamp=timestamp, description=description)

    async def wait(self, condition: str, timeout: int = 30000) -> bool:
        await self._ensure_started()
        from datetime import timedelta
        try:
            self._lib.wait_until_page_contains_element(
                self._locator(condition), timeout=timedelta(milliseconds=timeout)
            )
            return True
        except Exception:
            return False

    async def assert_visible(self, selector: str) -> bool:
        await self._ensure_started()
        try:
            self._lib.element_should_be_visible(self._locator(selector))
            return True
        except Exception:
            return False

    async def assert_text(self, selector: str, expected: str) -> bool:
        actual = await self.get_text(selector)
        return expected in actual

    async def close(self) -> None:
        if self._lib:
            self._lib.close_all_browsers()

    async def get_console_logs(self) -> List[Dict[str, Any]]:
        return self._console_logs.copy()

    async def get_network_logs(self) -> List[Dict[str, Any]]:
        return self._network_logs.copy()


class CypressAdapter(BrowserAdapter):
    """Cypress implementation - รัน `npx cypress run` จริง (ไม่ใช่ stub)

    Cypress ไม่มี interactive session แบบ Playwright/Selenium (แต่ละ
    `cypress run` เปิด-ปิด browser ของตัวเอง) เพื่อให้ยัง "จำ session" ได้
    เหมือน adapter อื่น adapter นี้ replay คำสั่งทั้งหมดที่เคยเรียกมา
    (visit/click/fill/...) เป็น Cypress spec เดียวทุกครั้งที่เรียก action ใหม่
    แล้วอ่านผลลัพธ์ของ action ล่าสุดกลับมาจากไฟล์ result.json ที่ spec เขียนออกมา

    ต้องมี Node.js + npx ในเครื่อง (`npx cypress` จะดาวน์โหลด Cypress เองถ้ายังไม่มี)
    """

    def __init__(self, headless: bool = True, project_dir: Optional[str] = None):
        self.headless = headless
        self._project_dir = Path(project_dir or "./.qa-mcp-cypress").resolve()
        self._result_path = self._project_dir.parent / "cypress-result.json"
        self._commands: List[str] = []
        self._project_ready = False

    def _ensure_project(self) -> None:
        if self._project_ready:
            return
        e2e_dir = self._project_dir / "cypress" / "e2e"
        support_dir = self._project_dir / "cypress" / "support"
        e2e_dir.mkdir(parents=True, exist_ok=True)
        support_dir.mkdir(parents=True, exist_ok=True)
        (support_dir / "e2e.js").touch()

        screenshots_folder = os.path.relpath(
            (self._project_dir.parent / "screenshots").resolve(), self._project_dir
        ).replace("\\", "/")
        config = (
            "module.exports = {\n"
            "  video: false,\n"
            "  screenshotOnRunFailure: false,\n"
            f"  screenshotsFolder: {json.dumps(screenshots_folder)},\n"
            "  chromeWebSecurity: false,\n"
            "  e2e: { setupNodeEvents(on, config) { return config; } },\n"
            "};\n"
        )
        (self._project_dir / "cypress.config.js").write_text(config)
        self._project_ready = True

    async def _execute(self, cmd: str) -> Dict[str, Any]:
        """เพิ่มคำสั่งล่าสุดเข้า session, replay ทั้งหมด, คืนผลลัพธ์ของคำสั่งนี้"""
        self._ensure_project()
        self._commands.append(cmd)

        body = "\n".join(self._commands)
        spec = (
            'describe("qa-mcp session", () => {\n'
            '  it("replay", () => {\n'
            f"{body}\n"
            "  });\n"
            "});\n"
        )
        spec_path = self._project_dir / "cypress" / "e2e" / "session.cy.js"
        spec_path.write_text(spec)

        args = ["--yes", "cypress", "run", "--spec", "cypress/e2e/session.cy.js", "--browser", "electron"]
        if not self.headless:
            args.append("--headed")

        proc = await asyncio.create_subprocess_exec(
            "npx", *args,
            cwd=str(self._project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            tail = stdout.decode(errors="ignore")[-2000:]
            raise RuntimeError(f"Cypress run failed (exit {proc.returncode}):\n{tail}")

        if self._result_path.exists():
            return json.loads(self._result_path.read_text())
        return {}

    async def open(self, url: str, options: Optional[Dict] = None) -> Dict[str, Any]:
        result_file = json.dumps(str(self._result_path))
        cmd = (
            f"    cy.visit({json.dumps(url)});\n"
            "    cy.title().then((title) => {\n"
            "      cy.location().then((loc) => {\n"
            f"        cy.writeFile({result_file}, {{ status: 200, url: loc.href, title: title }});\n"
            "      });\n"
            "    });"
        )
        result = await self._execute(cmd)
        return {"status": result.get("status", 200), "url": result.get("url", url), "title": result.get("title", "")}

    async def click(self, selector: str, options: Optional[Dict] = None) -> Dict[str, Any]:
        result_file = json.dumps(str(self._result_path))
        cmd = (
            f"    cy.get({json.dumps(selector)}).click();\n"
            f"    cy.writeFile({result_file}, {{ success: true, selector: {json.dumps(selector)} }});"
        )
        await self._execute(cmd)
        return {"success": True, "selector": selector}

    async def fill(self, selector: str, value: str) -> Dict[str, Any]:
        result_file = json.dumps(str(self._result_path))
        cmd = (
            f"    cy.get({json.dumps(selector)}).clear().type({json.dumps(value)});\n"
            f"    cy.writeFile({result_file}, {{ success: true, selector: {json.dumps(selector)}, "
            f"value: {json.dumps(value)} }});"
        )
        await self._execute(cmd)
        return {"success": True, "selector": selector, "value": value}

    async def select(self, selector: str, value: str) -> Dict[str, Any]:
        result_file = json.dumps(str(self._result_path))
        cmd = (
            f"    cy.get({json.dumps(selector)}).select({json.dumps(value)});\n"
            f"    cy.writeFile({result_file}, {{ success: true, selector: {json.dumps(selector)}, "
            f"value: {json.dumps(value)} }});"
        )
        await self._execute(cmd)
        return {"success": True, "selector": selector, "value": value}

    async def get_text(self, selector: str) -> str:
        result_file = json.dumps(str(self._result_path))
        cmd = (
            f"    cy.get({json.dumps(selector)}).then(($el) => {{\n"
            f"      cy.writeFile({result_file}, {{ text: $el.text() }});\n"
            "    });"
        )
        result = await self._execute(cmd)
        return result.get("text", "")

    async def screenshot(self, name: str, description: str = "") -> ScreenshotEvidence:
        result_file = json.dumps(str(self._result_path))
        cmd = (
            "    cy.screenshot('qa-mcp-shot', { capture: 'viewport', overwrite: true });\n"
            f"    cy.writeFile({result_file}, {{ screenshot: true }});"
        )
        await self._execute(cmd)

        from datetime import datetime
        timestamp = datetime.now().isoformat()
        safe_timestamp = timestamp.replace(":", "-")
        dest = Path(f"./screenshots/{name}_{safe_timestamp}.png")
        dest.parent.mkdir(parents=True, exist_ok=True)

        src = self._project_dir.parent / "screenshots" / "session.cy.js" / "qa-mcp-shot.png"
        if src.exists():
            shutil.move(str(src), str(dest))
        return ScreenshotEvidence(path=str(dest), timestamp=timestamp, description=description)

    async def wait(self, condition: str, timeout: int = 30000) -> bool:
        result_file = json.dumps(str(self._result_path))
        cmd = (
            f"    cy.get('body', {{ timeout: {timeout} }}).then(($body) => {{\n"
            f"      const found = $body.find({json.dumps(condition)}).length > 0;\n"
            f"      cy.writeFile({result_file}, {{ found }});\n"
            "    });"
        )
        result = await self._execute(cmd)
        return bool(result.get("found", False))

    async def assert_visible(self, selector: str) -> bool:
        result_file = json.dumps(str(self._result_path))
        cmd = (
            "    cy.get('body').then(($body) => {\n"
            f"      const visible = $body.find({json.dumps(selector)}).filter(':visible').length > 0;\n"
            f"      cy.writeFile({result_file}, {{ selector: {json.dumps(selector)}, visible }});\n"
            "    });"
        )
        result = await self._execute(cmd)
        return bool(result.get("visible", False))

    async def assert_text(self, selector: str, expected: str) -> bool:
        result_file = json.dumps(str(self._result_path))
        cmd = (
            "    cy.get('body').then(($body) => {\n"
            f"      const text = $body.find({json.dumps(selector)}).first().text();\n"
            f"      cy.writeFile({result_file}, {{ text, contains: text.includes({json.dumps(expected)}) }});\n"
            "    });"
        )
        result = await self._execute(cmd)
        return bool(result.get("contains", False))

    async def close(self) -> None:
        """Cypress ไม่มี process ค้างให้ปิด (แต่ละ run จบแล้ว browser ปิดเอง) - แค่เคลียร์ session ที่จำไว้"""
        self._commands = []

    async def get_console_logs(self) -> List[Dict[str, Any]]:
        return []

    async def get_network_logs(self) -> List[Dict[str, Any]]:
        return []


class BrowserFactory:
    """Factory สร้าง browser adapter ตาม framework

    Adapter ถูก cache ไว้เป็น singleton ต่อ framework ภายใน process เดียวกัน
    เพื่อให้ browser.open / browser.click / browser.fill / browser.screenshot /
    browser.assert ที่เรียกต่อเนื่องกันใช้ browser session (และ page) เดียวกันจริง ๆ
    แทนที่จะเปิด browser ใหม่ทุกครั้งจนไม่มี element ให้ทดสอบ
    """

    _instances: Dict[str, BrowserAdapter] = {}

    @classmethod
    def create(cls, framework: str = "playwright", **kwargs) -> BrowserAdapter:
        framework = framework.lower()
        if framework in cls._instances:
            return cls._instances[framework]

        if framework == "playwright":
            adapter: BrowserAdapter = PlaywrightAdapter(**kwargs)
        elif framework == "selenium":
            adapter = SeleniumAdapter(**kwargs)
        elif framework == "robot" or framework == "robotframework":
            adapter = RobotFrameworkAdapter(**kwargs)
        elif framework == "cypress":
            adapter = CypressAdapter(**kwargs)
        else:
            raise ValueError(f"Unsupported framework: {framework}")

        cls._instances[framework] = adapter
        return adapter

    @classmethod
    async def close(cls, framework: str = "playwright") -> bool:
        """ปิด browser session ที่ cache ไว้ และล้าง cache"""
        framework = framework.lower()
        adapter = cls._instances.pop(framework, None)
        if adapter is None:
            return False
        await adapter.close()
        return True

    @classmethod
    async def close_all(cls) -> None:
        for framework in list(cls._instances):
            await cls.close(framework)


# MCP Tools
async def browser_open(url: str, framework: str = "playwright") -> Dict[str, Any]:
    """MCP tool: browser.open"""
    browser = BrowserFactory.create(framework)
    result = await browser.open(url)
    return result


async def browser_click(selector: str, framework: str = "playwright") -> Dict[str, Any]:
    """MCP tool: browser.click"""
    browser = BrowserFactory.create(framework)
    return await browser.click(selector)


async def browser_fill(selector: str, value: str, framework: str = "playwright") -> Dict[str, Any]:
    """MCP tool: browser.fill"""
    browser = BrowserFactory.create(framework)
    return await browser.fill(selector, value)


async def browser_assert(selector: str, framework: str = "playwright") -> Dict[str, Any]:
    """MCP tool: browser.assert"""
    browser = BrowserFactory.create(framework)
    visible = await browser.assert_visible(selector)
    return {"selector": selector, "visible": visible}


async def browser_screenshot(name: str, framework: str = "playwright") -> Dict[str, Any]:
    """MCP tool: browser.screenshot"""
    browser = BrowserFactory.create(framework)
    evidence = await browser.screenshot(name)
    return {"path": evidence.path, "timestamp": evidence.timestamp}


async def browser_close(framework: str = "playwright") -> Dict[str, Any]:
    """MCP tool: browser.close - ปิด browser session ที่เปิดค้างไว้"""
    closed = await BrowserFactory.close(framework)
    return {"framework": framework, "closed": closed}
