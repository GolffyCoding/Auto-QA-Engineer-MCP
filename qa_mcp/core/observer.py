"""
Core: TestObserver
สังเกตและเก็บ evidence ระหว่างการทดสอบ
"""
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Observation:
    """ข้อมูลที่สังเกตได้"""
    timestamp: str
    event_type: str  # page_load, click, api_call, error, screenshot
    data: Dict[str, Any] = field(default_factory=dict)


class TestObserver:
    """Observer สำหรับ real-time monitoring"""

    def __init__(self):
        self._observations: List[Observation] = []
        self._subscribers: List[Callable] = []

    def subscribe(self, callback: Callable[[Observation], None]):
        self._subscribers.append(callback)

    def observe(self, event_type: str, data: Dict[str, Any]):
        obs = Observation(
            timestamp=datetime.now().isoformat(),
            event_type=event_type,
            data=data,
        )
        self._observations.append(obs)
        for sub in self._subscribers:
            try:
                sub(obs)
            except:
                pass

    def get_observations(self, event_type: Optional[str] = None) -> List[Observation]:
        if event_type:
            return [o for o in self._observations if o.event_type == event_type]
        return self._observations

    def get_timeline(self) -> List[Dict[str, Any]]:
        return [{
            "timestamp": o.timestamp,
            "event": o.event_type,
            "data": o.data,
        } for o in self._observations]
