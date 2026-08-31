"""Safe smoke test: status -> stop -> tiny command -> stop.
Run only with wheels lifted or motor VM disconnected.
"""
from __future__ import annotations

import os
import time
import requests

BASE = os.environ.get("ESP32_BASE_URL", "http://192.168.1.90")

print("STATUS", requests.get(f"{BASE}/api/status", timeout=2).json())
print("STOP", requests.post(f"{BASE}/api/stop", timeout=2).json())
print("LOW FORWARD", requests.post(
    f"{BASE}/api/command",
    json={"left": 12, "right": 12, "ttl_ms": 400, "seq": 1},
    timeout=2,
).json())
time.sleep(0.25)
print("STOP", requests.post(f"{BASE}/api/stop", timeout=2).json())
