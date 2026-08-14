"""
Persistence layer - ทำให้ state ของ qa-mcp รอด process restart ได้จริง

เดิม TestExecutor/DefectTracker/FixEngine/FailureAnalyzer เก็บทุกอย่างใน
memory ของ process เดียว (แก้ statelessness-ข้าม-call ไปแล้วในรอบก่อน แต่ยัง
ไม่รอด restart) - โมดูลนี้เพิ่ม JSON-file-backed store แบบเดียวกับที่
`qa_mcp.knowledge.base.KnowledgeBase` ใช้อยู่แล้ว (real, working pattern ที่
มีอยู่ในโค้ดเดิมแต่ไม่เคยถูกเอาไปใช้ที่อื่น) มาใช้ร่วมกันทุก module ที่ต้องการ
persist state

Default path มาจาก env var `QA_MCP_STATE_DB` - ตั้งเป็นคนละไฟล์ต่อ
โปรเจกต์/ทีมได้ เพื่อไม่ให้ state ของงานคนละงานปนกัน
"""
import contextlib
import json
import os
from typing import Any, Dict

try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:  # pragma: no cover - POSIX-only; no-op elsewhere
    _HAS_FCNTL = False


def default_state_path() -> str:
    return os.environ.get("QA_MCP_STATE_DB", "./qa-mcp-state.json")


@contextlib.contextmanager
def _file_lock(lock_path: str):
    """Cross-process advisory lock (POSIX flock) รอบ read-merge-write ของ
    save() - จำเป็นเมื่อทั้งทีมชี้ QA_MCP_STATE_DB ไปที่ไฟล์เดียวกัน (หลาย
    `qa-mcp-serve` process, คนละ engineer, รัน parallel) ไม่งั้นสอง process
    ที่ save() พร้อมกันอาจ race กัน (อ่าน-แก้-เขียนทับกันเอง) แม้จะ merge
    namespace ถูกต้องแล้วก็ตาม
    """
    if not _HAS_FCNTL:
        yield
        return
    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


class PersistentStore:
    """JSON-file-backed key-value store แบ่งเป็น namespace (ต่อ module)

    หลาย module (TestExecutor, DefectTracker, FixEngine, FailureAnalyzer)
    ต่างสร้าง PersistentStore ของตัวเอง แต่ชี้ไปที่ไฟล์เดียวกัน (เพราะเป็น
    singleton คนละตัวกัน) - ถ้า save() เขียนทับทั้งไฟล์ตรง ๆ แบบ naive จะทำให้
    instance ที่ save() หลังสุดล้าง namespace ของ instance อื่นทิ้งหมด (bug ที่
    เจอจริงตอนทดสอบ) จึงต้องทำ read-merge-write: อ่านไฟล์ล่าสุดจากดิสก์ก่อน
    เขียนทับเฉพาะ namespace ที่ instance นี้เป็นเจ้าของ แล้วค่อยเขียนกลับ
    """

    def __init__(self, path: str = ""):
        self.path = path or default_state_path()
        self._data: Dict[str, Dict[str, Any]] = self._read_from_disk()
        self._owned_namespaces: set = set()

    def _read_from_disk(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def save(self) -> None:
        """Read-merge-write ภายใต้ cross-process lock: เอา namespace ที่
        instance นี้เป็นเจ้าของทับลงบนข้อมูลล่าสุดจากดิสก์ (กัน instance อื่น
        ที่เขียนไปก่อนหน้าถูกล้างทิ้ง, และกัน process อื่นเขียนแทรกกลางคัน)

        สำคัญ: namespace ที่เราเป็นเจ้าของต้อง merge เข้า self._data[ns] แบบ
        in-place (mutate dict เดิม) ห้าม reassign เป็น dict ใหม่ - caller
        อย่าง TestExecutor/DefectTracker/FixEngine เรียก namespace() แค่ครั้ง
        เดียวตอน __init__ แล้วถือ reference นั้นไว้ mutate ยาว ๆ ตลอดอายุ
        process ถ้า save() reassign self._data เป็น dict ใหม่ (ของเดิมที่ทำ)
        reference เดิมที่ caller ถืออยู่จะหลุดออกจาก self._data ทันทีหลัง
        save() ครั้งแรก - save() ครั้งต่อไปจะเขียนค่าเก่าซ้ำ ๆ ไม่เห็นการ
        เปลี่ยนแปลงใหม่เลย (data loss แบบเงียบ ๆ - เจอจริงตอนเทส TestExecutor
        เขียนผลลัพธ์ test 2 ตัวเข้า run เดียวกัน ตัวที่สองหายจากดิสก์)
        """
        with _file_lock(f"{self.path}.lock"):
            current = self._read_from_disk()

            for ns in self._owned_namespaces:
                target = self._data.setdefault(ns, {})
                for key, value in current.get(ns, {}).items():
                    target.setdefault(key, value)

            for ns, value in current.items():
                if ns not in self._owned_namespaces:
                    self._data[ns] = value

            tmp_path = f"{self.path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.path)

    def namespace(self, name: str) -> Dict[str, Any]:
        """คืน dict ที่ mutate ได้โดยตรง (อยู่ใน self._data จริง ไม่ใช่ copy)
        - แก้ dict นี้แล้วเรียก .save() เพื่อเขียนลงดิสก์ - เรียกครั้งแรกจะ
        mark ว่า instance นี้เป็นเจ้าของ namespace นี้ (สำหรับ merge ตอน save)
        """
        self._owned_namespaces.add(name)
        return self._data.setdefault(name, {})
