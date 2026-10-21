from __future__ import annotations

import os
import threading
import time
from uuid import UUID

_lock = threading.Lock()
_last_timestamp = 0


def new_id() -> UUID:
    global _last_timestamp
    now = time.time_ns()
    timestamp = (now // 1_000_000) << 12 | (now % 1_000_000) * 4096 // 1_000_000
    with _lock:
        timestamp = max(timestamp, _last_timestamp + 1)
        _last_timestamp = timestamp
    random_bits = int.from_bytes(os.urandom(8)) & ((1 << 62) - 1)
    return UUID(
        int=(timestamp >> 12) << 80
        | 0x7 << 76
        | (timestamp & 0xFFF) << 64
        | 0b10 << 62
        | random_bits
    )
