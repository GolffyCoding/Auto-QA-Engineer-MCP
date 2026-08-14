# 🤖 Autonomous QA Engineer MCP

**Autonomous QA Engineer MCP** เป็น QA Engineering Runtime สำหรับ LLM Agent ที่ทำหน้าที่เป็น "วิศวกร QA อัตโนมัติ" ตั้งแต่การสแกนโปรเจกต์ วางแผนทดสอบ สร้าง test case รันทดสอบ วิเคราะห์ failure ไปจนถึงเสนอ patch แก้ไข — ครบวงจรผ่าน [Model Context Protocol](https://modelcontextprotocol.io/) (MCP)

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-active--development-orange)
![Tests](https://img.shields.io/badge/tests-91%20passing-brightgreen)

---

## ✨ ทำอะไรได้บ้าง

| ขั้นตอน | ความสามารถ |
|---------|------------|
| 🔍 **Understand** | สแกนและเข้าใจโครงสร้างโปรเจกต์ ตรวจจับ tech stack อัตโนมัติ |
| 🧠 **Plan** | วางแผนกลยุทธ์การทดสอบตามความเสี่ยงและ coverage |
| 🛠️ **Generate** | ระบบสร้าง edge case/worst case/security case ให้เองตามหลักการ (BVA, Equivalence Partitioning, OWASP) — LLM แค่บอก field spec, ไม่ต้องคิดเคสพื้นฐานเอง |
| ▶️ **Execute** | รัน automation test ผ่าน Playwright / Selenium / Robot Framework / Cypress (browser) และ REST (API) |
| 👁️ **Observe** | เก็บหลักฐาน (screenshot, log, trace) ระหว่างรันเทส |
| 🩺 **Diagnose** | วิเคราะห์สาเหตุที่แท้จริงของ failure |
| 🔧 **Fix** | เสนอและ apply patch เพื่อแก้ปัญหาโดยอัตโนมัติ |
| ✅ **Verify** | รัน regression test เพื่อยืนยันว่าแก้ได้จริง |
| 📊 **Report** | สร้างรายงาน defect และเชื่อมต่อ CI/CD |

---

## 🏗️ Architecture

```
                    LLM Agent
                        │
                        ▼
                 QA MCP Server  ◄── entry point: qa-mcp
                        │
                  QA Domain API
                        │
        ┌───────────────┼───────────────┐
        │               │               │
     Browser           API            Mobile
        │               │               │
        ▼               ▼               ▼
    Playwright         REST          Appium
    Selenium          k6 (load)      Maestro
    Robot Framework
    Cypress
```

> รายละเอียดสถานะจริง (✅ ใช้งานได้จริง / 🔴 ยังไม่มีโค้ด) ของแต่ละ framework อยู่ที่หัวข้อ [🧭 Framework Support](#-framework-support) ด้านล่าง — ไดอะแกรมนี้แสดงแค่ภาพรวมสถาปัตยกรรม

โมดูลทั้งหมดถูกลงทะเบียนเป็น **tools** ให้ LLM เรียกใช้ — มี 2 ทางเข้าใช้งาน:

| Entry point | ใช้ทำอะไร | State ข้าม tool call |
|---|---|---|
| `qa-mcp` (`qa_mcp/mcp_server.py`) | CLI debug/ทดสอบ tool ทีละตัว | ❌ คนละ process ทุกครั้งที่ `--call` |
| `qa-mcp-serve` (`qa_mcp/server.py`) | **MCP server จริง** ผ่าน stdio ให้ LLM client (Claude Desktop, Claude Code, ฯลฯ) ต่อเข้ามา | ✅ process เดียว รันยาว — จำ session ได้ |

---

## 🚀 Quick Start

```bash
# ติดตั้งแบบ editable
pip install -e .

# ดู CLI options
qa-mcp --help

# แสดง tool ทั้งหมดที่ LLM เรียกใช้ได้
qa-mcp --list-tools

# เรียก tool ตรง ๆ ผ่าน CLI (เช่น สแกนโปรเจกต์) - ใช้ debug ทีละ tool
qa-mcp --call project.scan --args '{"project_path": "."}'
```

## 🧠 Test Case Generation: ใครรับผิดชอบอะไร

`test.generate` **ไม่ปล่อยให้ LLM คิด edge case/worst case/security case/business logic/UX/state cycle เอง** — เพราะ LLM อาจลืมเคสพื้นฐาน หรือคิดไม่ครบทุกครั้ง ระบบจึงเป็นคน generate เคสเหล่านี้ให้ deterministic ทุกครั้งตามหลักการที่ยอมรับกันในวงการ QA ครอบคลุม 5 มิติที่ LLM ป้อนเข้ามาได้อิสระ (จะใช้กี่มิติก็ได้ ใช้ร่วมกันได้ทั้งหมด):

| มิติ input (LLM ป้อน) | ระบบ generate อะไร | หลักการ |
|---|---|---|
| `fields` | Positive, required-field negative, boundary (BVA), type-mismatch negative, security injection probes | Boundary Value Analysis, Equivalence Partitioning, OWASP Top 10 |
| `business_rules` | เคสยืนยันว่า invariant คงอยู่ (positive) + เคสพยายามละเมิดแล้วต้องถูกสกัด (negative) | Business Logic invariant testing |
| `roles` | เคส access control ต่อ role (allowed/denied) | OWASP A01:2021 Broken Access Control |
| `ux_states` | เคสตรวจ UI state (loading/empty/error/offline/disabled/success/concurrent) | UX heuristics (Nielsen: visibility of system status, error prevention) |
| `states` | **ครบทุก (state × action) combination จริง** — ทุก transition ที่ประกาศไว้ (positive) + ทุก action ที่ไม่ถูกต้องจากทุก state (negative, exhaustive) + ตรวจหา unreachable state อัตโนมัติ | State-machine exhaustive coverage (graph reachability) |

**หน้าที่ของ LLM คือ "รายงานข้อเท็จจริง" ของ feature นั้นแบบ dynamic ตามงานจริง** (อ่านโค้ด/UI/spec แล้วบอกว่ามี field/business rule/role/UX state อะไรบ้าง) — ไม่ใช่คิด test case เอง ระบบเป็นคนขยายแต่ละข้อเท็จจริงเป็น test case ที่มี `rationale` กำกับเสมอ:

```python
await session.call_tool("test.generate", {
    "feature": "checkout",
    "fields": [
        {"name": "coupon_code", "type": "text", "required": False, "max_length": 20},
        {"name": "amount", "type": "number", "required": True},
    ],
    "business_rules": [
        {"name": "no-negative-total", "rule": "order total must never go below 0",
         "violation": "Apply a coupon larger than the order subtotal"},
    ],
    "roles": [
        {"role": "customer", "should_access": True},
        {"role": "guest", "should_access": False},
    ],
    "ux_states": ["loading", "empty", "error", "concurrent"],
})
```

ตัวอย่างข้างบนสร้างให้อัตโนมัติ **25 test cases** ครบทั้ง 7 category (Positive, Negative, Boundary, Security, Business Logic, Access Control, UX State) — ทุกเคสมี `rationale` เช่น:

> Business Logic: `"an invariant that is only checked on the happy path isn't actually enforced - it must be proven to hold under an explicit attempt to break it"`
> Access Control: `"OWASP A01:2021: an endpoint that merely checks authentication (not authorization) silently permits privilege escalation"`
> UX: `"an unindicated wait reads as a frozen/broken UI, and an un-disabled control invites duplicate/double-submit actions"`

ถ้าเรียก `test.generate` โดยไม่ส่งข้อมูลมิติไหนเลย และ feature ไม่ใช่ `"login"` (มี built-in preset) หรือไม่ใช่ API endpoint (`/...`, `http...`) ระบบจะ**ไม่เดา** — ตอบ error พร้อมตัวอย่างครบทั้ง 5 มิติแทน (ของเดิมเคยเดาแล้วสร้าง test case ผิดๆ แบบเงียบ ๆ — แก้เป็น fail-fast แล้ว)

`test.analyze_coverage` ก็แก้บั๊กเดียวกัน — เดิมใช้ suite ของ "login" เป็น reference เสมอไม่ว่าจะวิเคราะห์ feature อะไร ตอนนี้ต้องส่ง `fields` ที่ตรงกับ feature จริง (ยกเว้น login ที่มี preset)

### State Cycle: ตัวอย่าง "ครบทุกเคส" จริง ๆ

```python
await session.call_tool("test.generate", {
    "feature": "order-status",
    "states": {
        "initial": "pending",
        "transitions": [
            {"from": "pending", "to": "paid", "action": "complete_payment"},
            {"from": "paid", "to": "shipped", "action": "ship_order"},
            {"from": "shipped", "to": "delivered", "action": "confirm_delivery"},
            {"from": "pending", "to": "cancelled", "action": "cancel_order"},
            {"from": "paid", "to": "cancelled", "action": "cancel_order"},
        ],
    },
})
```

จาก 5 transition ที่ประกาศ (5 state: pending/paid/shipped/delivered/cancelled × 4 action: complete_payment/ship_order/confirm_delivery/cancel_order = 20 combination เต็ม matrix) ระบบสร้างให้ **20 test cases**: 5 positive (ทุก transition ที่ประกาศจริง) + 15 negative (ทุก combination ที่ไม่ valid ต้องถูกบล็อก — คูณ matrix เต็ม ไม่ใช่สุ่มเลือกบางอัน) ในตัวอย่างนี้ทุก state reach ได้จาก `initial` เลยไม่มีเคส Regression แจ้งเตือน — แต่ถ้ามี state ที่ unreachable จริง (ทดสอบแล้วด้วย state machine ที่จงใจใส่ state `refunded`/`closed` ที่ไม่มี transition เข้าถึง) ระบบเจอและแจ้งเตือนถูกต้อง 100%

---

## 🔁 ใช้งานกับ LLM แบบ Loop จริง (MCP over stdio)

`qa-mcp-serve` คือ MCP server ตัวจริง (ใช้ [official MCP Python SDK](https://pypi.org/project/mcp/)) ที่รันเป็น process เดียวยาว ๆ — LLM agent ต่อเข้ามาครั้งเดียวแล้วเรียก tool ต่อกันเป็น loop ได้ตามธรรมชาติ (scan → generate → open browser → click/fill/screenshot → assert → close, หรือ diagnose → propose → approve → apply_patch → verify) เพราะ state (browser page, patch proposals, defect tracker) อยู่ใน process เดียวกันตลอด ไม่หายไปทุกครั้งเหมือน `--call`

**รันเปล่า ๆ (LLM client เป็นคนสั่ง stdin/stdout เอง):**
```bash
qa-mcp-serve
```

**เชื่อมกับ Claude Desktop / Claude Code** — เพิ่มใน MCP config (`claude_desktop_config.json` หรือ `.mcp.json`):
```json
{
  "mcpServers": {
    "qa-mcp": {
      "command": "qa-mcp-serve"
    }
  }
}
```

**เชื่อมจาก Python client เอง (เช่นเขียน agent loop เอง):**
```python
import asyncio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

async def main():
    params = StdioServerParameters(command="qa-mcp-serve")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("browser.open", {"url": "https://example.com"})
            await session.call_tool("browser.click", {"selector": "a"})   # page เดิม ยังเปิดอยู่
            await session.call_tool("browser.screenshot", {"name": "proof"})
            await session.call_tool("browser.close")

asyncio.run(main())
```

ทดสอบแล้วว่าใช้งานได้จริงผ่าน MCP protocol เต็มรูปแบบ (`initialize` → `list_tools` พร้อม JSON schema ที่ถูกต้อง → `call_tool` ต่อเนื่องในเซสชันเดียว ได้ผลลัพธ์จริงจาก Playwright)

---

## 🐛 Bug / Error Finder (`failure_analysis`)

`failure.inspect`/`failure.classify` จัดหมวดหมู่ failure ด้วย **weighted pattern matching** ครอบคลุม 15 category (จากเดิมมีแค่ 5 category และมี pattern ทับซ้อนกันจนจัดหมวดผิดแบบสุ่มได้ — แก้แล้วด้วยระบบ weight ที่ pattern เจาะจงชนะ pattern ทั่วไปเสมอ):

`database` · `api` · `auth` · `validation` · `ui` · `browser` · `network` · `concurrency` · `resource` · `filesystem` · `configuration` · `third_party` · `mobile` · `security` · `logic`

ทุก category มี `likely_cause`/`suggested_fix` เฉพาะทางของตัวเอง (ไม่ใช่ fallback "Review code and logs" เหมือนเดิม) เช่น `concurrency` → "Add locking/transaction isolation or idempotency keys to prevent duplicate/racing operations"

**แก้ 2 ฟังก์ชันที่เป็น stub เดิม (ไม่เคยทำงานจริง) ให้ทำงานจริง:**
- `failure.get_evidence` — เดิม return `None` เสมอไม่ว่าจะเรียก `failure.inspect` ไปแล้วกี่ครั้ง (ไม่เคยเก็บอะไรไว้จริง) → ตอนนี้เก็บ evidence จริงและดึงคืนได้
- `failure.compare_runs` — เดิม return list ว่างเสมอไม่สนใจ input เลย → ตอนนี้ดึง `TestRun` จริงจาก `test.create_run`/`test.run` มาเทียบ ให้ `new_failures`/`fixed_failures`/`still_failing` ที่ถูกต้องจริง (ทดสอบแล้ว: จงใจทำ regression กับ fix พร้อมกันใน 2 run เจอถูกทั้งคู่)

---

## 🏢 Enterprise Readiness

3 จุดที่ทำให้ระบบนี้ใช้ในบริษัทได้จริง (ไม่ใช่แค่ demo เดี่ยว ๆ):

### 1. Persistence จริง - state รอด restart

เดิมทุกอย่าง (test run, defect, patch proposal, failure evidence) อยู่ใน memory ของ process เดียว — ปิด `qa-mcp-serve` แล้วหายหมด ตอนนี้มี `qa_mcp/core/persistence.py` (JSON-file store, atomic write) เก็บทุกอย่างลงดิสก์จริง กำหนด path ได้ผ่าน env var `QA_MCP_STATE_DB` (ตั้งคนละไฟล์ต่อโปรเจกต์/ทีมได้)

ทดสอบจริง: สร้าง test run + defect + failure evidence + patch proposal ใน process หนึ่ง → **kill process นั้นทิ้ง** → เปิด process ใหม่ → เรียก `test.get_run`/`failure.get_evidence`/`report.generate` อ่านค่ากลับมาได้ครบทุกตัว

### 2. Multi-user safe จริง - ทดสอบด้วย concurrent write จริง

`qa-mcp-serve` ใช้ stdio transport ซึ่ง MCP client (Claude Desktop/Code) จะ spawn เป็น**คนละ process ต่อคนต่อ session อยู่แล้วโดยธรรมชาติ** — ไม่มีปัญหา state รั่วข้ามผู้ใช้แบบที่กังวลไว้ตอนแรก แต่ถ้าทั้งทีมชี้ `QA_MCP_STATE_DB` ไปที่ไฟล์เดียวกัน (เพื่อเห็น defect/test run ของกันและกัน) หลาย process เขียนไฟล์เดียวกันพร้อมกันได้จริง จึงเพิ่ม:
- **Cross-process file lock** (`fcntl.flock`) รอบการเขียนทุกครั้ง
- **Entry-level merge** (ไม่ใช่ namespace-level replace) กัน process ที่ save() ทีหลังเขียนทับ record ของ process อื่น
- **Unique ID generation** — ของเดิม `defect_id`/`run_id`/`patch_id` ใช้ timestamp ความละเอียดวินาทีเดียว ชนกันจริงถ้าสร้างพร้อมกัน (เจอบั๊กจริงตอนทดสอบ) → เพิ่ม random suffix กันชน

ทดสอบจริง: spawn **8 process พร้อมกัน** สร้าง defect ลงไฟล์ state เดียวกัน — เดิมรอดแค่ 1/8 (เขียนทับกันเอง) หลังแก้รอด **8/8**

### 3. CI/CD trigger จริง (ไม่ใช่ stub)

`ci.run`/`ci.get_status` เดิม return `{"status": "triggered"}` คงที่เสมอ ไม่เคยยิงไปที่ไหนจริง ตอนนี้เรียก REST API จริงของ GitHub Actions (`workflow_dispatch`) และ GitLab CI (`trigger/pipeline`) ต้องตั้งค่า `GITHUB_TOKEN` หรือ `GITLAB_TRIGGER_TOKEN`/`GITLAB_API_TOKEN` ตามจริง

ทดสอบจริง: ยิงไปที่ GitHub API ด้วย token ปลอม ได้ `401 Bad credentials` กลับมาจริงจาก GitHub server (พิสูจน์ว่าเป็น network call จริง ไม่ใช่ mock) และตอนไม่มี token เลยจะได้ error บอกวิธีตั้งค่าแทนที่จะแกล้งสำเร็จ

---

## 🧭 Framework Support

`browser.open` / `browser.click` / `browser.fill` / `browser.screenshot` / `browser.assert` / `browser.close` ทุกตัวรับ parameter `framework` เดียวกัน สลับ engine ได้โดยไม่ต้องเปลี่ยนวิธีเรียก:

| Framework | `framework=` | สถานะ | ต้องมีอะไรในเครื่อง |
|---|---|---|---|
| **Playwright** | `"playwright"` (default) | ✅ ใช้งานได้จริง | `playwright install` (ติดตั้ง browser binaries) |
| **Selenium** | `"selenium"` | ✅ ใช้งานได้จริง | ChromeDriver / Chrome ในเครื่อง |
| **Robot Framework** | `"robot"` หรือ `"robotframework"` | ✅ ใช้งานได้จริง (ผ่าน `SeleniumLibrary` โดยตรง ไม่ต้องเขียนไฟล์ `.robot`) | Chrome ในเครื่อง (ใช้ driver เดียวกับ Selenium) |
| **Cypress** | `"cypress"` | ✅ ใช้งานได้จริง (สั่ง `npx cypress run` จริงทุกครั้ง, ไม่ใช่ stub) | Node.js + npx (จะดาวน์โหลด Cypress ให้อัตโนมัติครั้งแรกที่ใช้) |

> Cypress ทำงานต่างจาก 3 ตัวแรกภายใน: แต่ละครั้งที่เรียก action ใหม่ (`click`, `fill`, …) adapter จะ **replay คำสั่งทั้งหมดที่เคยเรียกมาในเซสชันนี้** เป็น Cypress spec เดียวแล้วรันใหม่ทั้งชุด (เพราะ Cypress ไม่มี interactive session ข้ามคำสั่งแบบ Playwright/Selenium) — ผลลัพธ์ยังถูกต้องและใช้งานได้จริง แต่จะช้าลงเรื่อย ๆ ตามจำนวน action ในเซสชัน ถ้าต้องการ workflow ยาวมาก แนะนำ Playwright/Selenium/Robot Framework แทน
>
> ตัวอย่าง: `qa-mcp-serve` แล้วเรียก `browser.open({"url": "...", "framework": "cypress"})` ตามด้วย `browser.click({"selector": "a", "framework": "cypress"})` — ทดสอบแล้วว่าคลิกจริง navigate จริง และ `browser.assert`/`browser.screenshot` ให้ผลลัพธ์จริงจากหน้าเว็บ ไม่ใช่ค่าคงที่

### API / Load Testing

| Tool | สถานะ | ต้องมีอะไรในเครื่อง |
|---|---|---|
| `api.request` (REST ผ่าน httpx) | ✅ ใช้งานได้จริง | - |
| `api.load_test` (k6) | ✅ ใช้งานได้จริง — สั่ง `k6 run` จริงทุกครั้ง ไม่ใช่ค่าคงที่ | k6 binary ในเครื่อง (หรือกำหนด path ผ่าน `QA_MCP_K6_BIN`) |
| Postman/Newman, JMeter | 🔴 ยังไม่มีโค้ด | - |

`api.load_test({"url", "vus", "duration"|"iterations"})` รัน k6 จริงแล้วคืนสถิติจริง (latency p95, requests/sec, failed rate) ต่างจาก `api.request` ตรงที่ยิงพร้อมกันหลาย virtual users เพื่อวัด load ไม่ใช่ยิงทีละ request

### Mobile

| Framework | สถานะ | ต้องมีอะไรในเครื่อง |
|---|---|---|
| **Appium** (`framework="appium"`, default) | ✅ ใช้งานได้จริง (ต่อ Appium server ผ่าน Appium-Python-Client จริง) | Appium server รันอยู่ (`appium`) + device/emulator จริงที่ต่อผ่าน `adb` |
| **Maestro** (`framework="maestro"`) | ✅ ใช้งานได้จริง (generate flow YAML แล้วสั่ง `maestro test` จริง) | Maestro CLI ในเครื่อง + device/emulator จริง |

> ทั้งสองตัว **error ตรง ๆ เมื่อไม่มี Appium server / device ต่ออยู่** (ไม่ใช่ silent success แบบ stub เดิมที่คืน `{"success": true}` เสมอ) — ทดสอบใน sandbox นี้ (ไม่มี Android emulator) แล้วได้ error ที่ถูกต้องตามจริง เช่น Maestro ตอบ `"You have 0 devices connected"` และ Appium ตอบ connection refused ที่ port ของ Appium server — ยืนยันว่าโค้ดพยายามต่อ infrastructure จริง ไม่ใช่แกล้งสำเร็จ ต้องมี emulator/device จริงถึงจะรันจบ end-to-end ได้

### Test Reporting

`test.create_run` → `test.run`/`test.rerun` (หลายครั้ง) → `report.generate` / `report.generate_html` — ผลทุก test ที่รันในเซสชันเดียวกันจะรวมเข้า run เดียว แล้วสร้างรายงานสรุป pass/fail/duration จริงจากผลจริง (ไม่ใช่ mock):

```python
run = await session.call_tool("test.create_run", {"suite_name": "checkout-suite"})
await session.call_tool("test.run", {"test_id": "t1", "command": ["pytest", "test_login.py"]})
await session.call_tool("test.run", {"test_id": "t2", "command": ["pytest", "test_checkout.py"]})
report = await session.call_tool("report.generate_html", {"run_id": run_id})
# -> {"report_id": "...", "path": "./reports/report-....html", "summary": {...}}
```

`report.generate_html` เซฟไฟล์ HTML จริงลงดิสก์ (`./reports/`) พร้อมตาราง summary + failed tests — เปิดดูใน browser ได้ทันที ไม่ใช่แค่ raw JSON

### Database / Data Validation

ใช้ SQLAlchemy จริง (รองรับทุก DB ที่ SQLAlchemy รองรับผ่าน `connection_string`: PostgreSQL, MySQL, SQLite, ...) เพื่อ verify ข้อมูลหลังรัน E2E test:

| Tool | ใช้ทำอะไร |
|---|---|
| `db.get_table_state` | ดู row count / columns / sample rows ของ table จริง |
| `db.check_fk_integrity` | หา orphaned foreign key จริง (เช่น `orders.user_id` ที่ไม่มีอยู่ใน `users.id`) — คืน `status: "broken"` พร้อมจำนวนแถวที่ผิดจริง |
| `db.query` | รัน SELECT ตรง ๆ (read-only เท่านั้น — บล็อค INSERT/UPDATE/DELETE/DROP) สำหรับกรณีที่ query สำเร็จรูปไม่พอ |

ทดสอบแล้วด้วย SQLite จริงที่มี orphaned FK จงใจ (`orders.user_id = 999` ที่ไม่มีใน `users`) — `db.check_fk_integrity` เจอ `invalid_references: 1, status: "broken"` ถูกต้องตามจริง ป้องกัน SQL injection ผ่านชื่อ table/column ด้วย identifier allowlist (`[A-Za-z0-9_]+` เท่านั้น)

---

## 📦 Phases & Modules

| Phase | Module | Description |
|:-----:|--------|-------------|
| 1 | `project_intelligence` | สแกนและเข้าใจโปรเจกต์ / ตรวจจับ stack |
| 2 | `test_design` | สร้าง test case และวิเคราะห์ coverage |
| 3 | `adapters` | เลเยอร์นามธรรมสำหรับ automation engine (browser / api / mobile) |
| 4 | `execution` | ตัวรันเทสและวงจรชีวิตของ test run |
| 5 | `failure_analysis` | วิเคราะห์และหาสาเหตุของ failure |
| 6 | `fix_loop` | วงจรแก้ไขอัตโนมัติ: diagnose → propose → **approve** → apply → verify |
| 7 | `defect_cicd` | สร้าง defect report และเชื่อมต่อ git / CI/CD |
| 8 | `core.reporter` | สร้างรายงานสรุปผลการทดสอบ (JSON/HTML) |
| 9 | `analyzers.database_analyzer` | Verify ข้อมูลใน database จริงหลังรัน test |

## 🧰 ตัวอย่าง Tools ที่ลงทะเบียนไว้

```
project.scan            test.generate           browser.open
project.detect_stack    test.analyze_coverage   api.request
test.create              failure.inspect         fix_loop.diagnose
test.run                 failure.find_root_cause fix_loop.apply_patch
defect.create             git.status             ci.detect
```

ดูรายการทั้งหมด (พร้อม path ของฟังก์ชัน) ได้ด้วย `qa-mcp --list-tools`

---

## 🧪 Dependencies

โปรเจกต์นี้ต้องการ Python **3.10+** และใช้ไลบรารีหลักได้แก่ `mcp`, `pydantic`, `httpx`, `playwright`, `selenium`, `robotframework`, `robotframework-seleniumlibrary`, `Appium-Python-Client`, `pytest`, `sqlalchemy` และอื่น ๆ ตามที่ระบุใน [`requirements.txt`](requirements.txt)

Dependency ที่ไม่ใช่ Python (ติดตั้งแยกตามแต่ framework ที่จะใช้):
- **Cypress** — Node.js + `npx`
- **k6** — [k6 binary](https://k6.io/docs/get-started/installation/)
- **Appium** — Appium server (`npm install -g appium`) + Android/iOS SDK + device/emulator
- **Maestro** — [Maestro CLI](https://maestro.mobile.dev/getting-started/installing-maestro) + device/emulator

### Environment variables

| ตัวแปร | ใช้ทำอะไร |
|---|---|
| `QA_MCP_STATE_DB` | path ของไฟล์ persistence (default `./qa-mcp-state.json`) — ตั้งคนละไฟล์ต่อโปรเจกต์/ทีม หรือชี้ไปที่ path เดียวกันถ้าอยากให้ทั้งทีมเห็น defect/test run ร่วมกัน |
| `QA_MCP_K6_BIN` | path ของ k6 binary ถ้าไม่ได้อยู่ใน PATH มาตรฐาน |
| `GITHUB_TOKEN` | สำหรับ `ci.run`/`ci.get_status` กับ GitHub Actions (ต้องมีสิทธิ์ `actions:write`) |
| `GITLAB_TRIGGER_TOKEN` / `GITLAB_API_TOKEN` | สำหรับ `ci.run` (trigger token) / `ci.get_status` (API token) กับ GitLab CI |

> Cross-process file lock ของ persistence layer ใช้ `fcntl` (POSIX เท่านั้น — Linux/macOS) บน Windows จะข้าม lock ไปเงียบ ๆ (ยังเขียนไฟล์ได้ปกติ แต่ไม่ปลอดภัยกับ concurrent write จากหลาย process พร้อมกัน)

---

## 🧪 Running the test suite

```bash
pip install -e .
python -m pytest tests/ -v
```

`tests/` มี unit test จริง 74 ตัว ครอบคลุมทุกโมดูลหลักยกเว้นส่วนที่ต้องมี browser/mobile device จริงต่ออยู่ (`adapters/browser.py`, `adapters/mobile.py`):

- `test_fix_loop_engine.py` — patch **apply ไม่ได้** ถ้ายังไม่ผ่าน `approve()`, `read_only=True` (default) ไม่แตะไฟล์บนดิสก์จริง, MCP tool `fix_loop.apply_patch(read_only=False)` **ถูกบล็อกเสมอ** เว้นแต่ตั้ง `QA_MCP_ALLOW_AUTO_APPLY=1`
- `test_persistence.py` — state รอด process restart จริง, หลาย `PersistentStore` instance คนละ namespace ไม่เขียนทับกัน, และ regression test สำหรับบั๊ก data-loss ที่เจอ (ดูด้านล่าง)
- `test_test_design_generator.py` — BVA boundary ถูกต้อง (max/max+1), security probe จำกัดเฉพาะ field type ที่ inject ได้, state-machine matrix ครบ, unreachable state ถูกจับ
- `test_failure_analyzer.py` — weighted pattern matching เลือก category เจาะจงถูกต้อง, evidence persist ข้าม process, `compare_runs`/`find_regression` ถูกต้อง
- `test_executor.py` — รัน subprocess จริง (pass/fail/timeout), เขียน artifact ลงดิสก์จริง, นับ pass/fail ใน run ถูกต้อง, retry มี exponential backoff, state รอด restart
- `test_defect_manager.py` — Defect CRUD + persistence, `CIManager.detect()` จาก marker file จริง, `ci.run` **ปฏิเสธทันทีไม่ยิง network** ถ้าไม่มี token/repo, `GitManager` ต่อ git repo จริง (status/log/commit)
- `test_database_analyzer.py` — รันกับ SQLite จริง: หา orphaned FK จริง, บล็อก non-SELECT ใน `db.query`, บล็อก SQL injection ผ่านชื่อ table/column
- `test_api_adapter.py` — `RESTAdapter` ผ่าน fake HTTP transport (ไม่ยิง network จริง), JSON-schema assertion logic, k6 script generation, `_find_k6_binary` fail-fast เมื่อไม่มี binary

### บั๊ก data-loss จริงที่เจอระหว่างเขียน test (แก้แล้ว)

`PersistentStore.save()` เดิม reassign `self._data = current` (dict ใหม่) ทุกครั้งที่ save — แต่ `namespace()` คืน reference ของ dict เดิมให้ caller ถือไว้ยาว ๆ (ทุก module เรียก `namespace()` แค่ครั้งเดียวตอน `__init__` แล้ว mutate reference นั้นตลอดอายุ process) หลัง `save()` ครั้งแรก reference นั้นหลุดออกจาก `self._data` ทันที **save() ครั้งที่สองเป็นต้นไปเขียนค่าเก่าซ้ำ ๆ ไม่เห็นการเปลี่ยนแปลงใหม่เลย** — เจอจริงตอนเทส `TestExecutor` รัน 2 test เข้า run เดียวกัน ผลลัพธ์ตัวที่สองหายจากดิสก์ กระทบทุก module ที่ persist (`TestExecutor`, `DefectTracker`, `FixEngine`, `FailureAnalyzer`) แก้แล้วโดยให้ `save()` merge เข้า dict object เดิมแบบ in-place แทนการ reassign — มี regression test (`test_repeated_save_on_same_instance_keeps_writing_new_mutations`) ยืนยันแล้ว

- `test_browser_adapter.py` — รันกับ headless Chromium จริงผ่าน Playwright (มี `playwright install` ในเครื่องนี้แล้ว) กับ static HTML fixture (`tests/fixtures/form.html`) ไม่ mock อะไรเลย: `open` ได้ title/url จริง, `fill`+`click` แก้ DOM จริงแล้วอ่านกลับได้, `assert_visible`/`assert_text` ตรวจ element ที่ซ่อน/โผล่จริงตามการโต้ตอบจริง, `screenshot` เขียนไฟล์ PNG จริงลงดิสก์ (ตรวจ magic bytes), console log ถูกจับได้จริง, และ `BrowserFactory` singleton ทำให้ `browser.open → browser.fill → browser.click → browser.assert` (4 MCP tool call แยกกัน) ใช้ browser session/page เดียวกันจริงตามที่ design ไว้

ยังไม่ครอบคลุม: `adapters/mobile.py` (Appium/Maestro) — sandbox นี้ไม่มี Android/iOS emulator หรือ Appium server ต่ออยู่ ต้องมี device/emulator จริงถึงจะเทสแบบไม่ mock ได้ตาม philosophy เดียวกับที่ทำกับ browser ไปแล้ว

### บั๊กจริงที่เจอจากการรัน end-to-end workflow ทั้งระบบ (แก้แล้ว)

หลัง unit test ผ่านหมดแล้ว ลองรัน full workflow จริงผ่าน `QAMCPServer.call()` แบบเดียวกับที่ `qa-mcp-serve` จะทำ (scan → generate → run → diagnose → propose → approve → apply → defect → report) และรัน CLI จริงกับ repo ตัวเอง เจอบั๊ก 3 ตัวที่ unit test เดิมไม่ครอบคลุม เพราะเป็นบั๊กที่โผล่เฉพาะตอนเรียกผ่าน dynamic dispatch/JSON boundary จริง หรือตอน scan directory จริงที่มีไฟล์เยอะ:

1. **`project.scan` กับ `project_path="."` คืน `name: ""` เสมอ** — `Path(".").name` เป็น empty string ทั้งที่การ scan "โปรเจกต์ปัจจุบัน" คือการใช้งานที่พบบ่อยที่สุด แก้โดย resolve เป็น absolute path ก่อนอ่าน `.name`

2. **`project.scan`/`project.detect_stack` จัดว่า Python project เป็น `language: "Unknown"`** เพราะ scanner เดิมไม่กรอง `.git`/`node_modules`/`__pycache__`/`.venv` ออกจาก `rglob("*")` — ไฟล์ blob ที่ไม่มีนามสกุลใน `.git/objects` มีจำนวนมากกว่าไฟล์ `.py` จริง ทำให้ "extension ที่เจอบ่อยสุด" กลายเป็นค่าว่าง ไม่ตรงกับ language map เลย แก้โดยเพิ่ม `EXCLUDED_DIRS` และ helper `_walk()` ที่กรองออกทุกจุดที่เคยเรียก `rglob()` ตรง ๆ (กระทบ framework/auth/testing-tools/routes/endpoints/components/forms detection ทั้งหมดที่เคยเจอปัญหาเดียวกัน)

3. **`test.prioritize` crash ทันทีถ้าใช้ตาม workflow ธรรมชาติ (generate แล้ว prioritize ต่อ)** — `TestDesigner.prioritize()` เดิมเรียก `c.priority` ตรง ๆ ซึ่งใช้ได้กับ `TestCase` object เท่านั้น แต่ caller ทุกตัวที่ผ่าน MCP/CLI (รวมถึง `test.generate` เอง) ส่ง-รับเป็น JSON dict เสมอ พอเอา `cases` ที่ได้จาก `test.generate` ไปป้อนต่อ `test.prioritize` ตรง ๆ (ซึ่งเป็นขั้นตอนที่คาดว่าจะทำกันเป็นปกติ) จะได้ `AttributeError` ทันที แก้โดยรองรับทั้ง dict และ object พร้อมคืนผลเป็น dict เสมอ (JSON-serializable ผ่าน MCP)

ทั้งสามมี regression test แล้ว (`tests/test_project_scanner.py`, `tests/test_test_design_generator.py::test_prioritize_*`)

## 🔒 Approval gate: `fix_loop.apply_patch`

เดิม `fix_loop_apply_patch(patch_id, read_only=False)` รับค่า `read_only` จาก caller ตรง ๆ — หมายความว่า LLM agent เรียก `fix_loop.approve` ต่อด้วย `fix_loop.apply_patch(read_only=False)` ในเซสชันเดียวกันได้เลย โดยไม่มี human ตัวจริงเข้ามาเกี่ยวข้อง (`approved_by` เป็นแค่ string ที่ agent ตั้งเองได้ ไม่ใช่ identity check) ตอนนี้แก้แล้ว: `read_only=False` จะถูกปฏิเสธเสมอ เว้นแต่มี env var `QA_MCP_ALLOW_AUTO_APPLY=1` ตั้งไว้ในเครื่องที่รัน `qa-mcp-serve` ล่วงหน้า — ซึ่งเป็นสิ่งที่ agent เข้าไปตั้งเองจากใน tool call ไม่ได้

**สำหรับใช้งานในบริษัท**: อย่าตั้ง `QA_MCP_ALLOW_AUTO_APPLY=1` ไว้ตลอดเวลาใน environment ที่ agent รันอยู่ ให้ human ตั้งค่านี้เฉพาะตอนที่ต้องการอนุมัติจริง ๆ แล้วเอาออกหลังใช้เสร็จ หรือ wrap เป็น approval workflow แยกต่างหาก (เช่น CI job ที่ set env var นี้เฉพาะตอนมี PR approval จาก reviewer จริง)

## 📄 License

MIT
