import json
import os
import time
from collections import deque
from pathlib import Path

# bot_id -> deque of status strings
_TICK_LOGS: dict[str, deque] = {}
_LAST_SAMPLE: dict[str, float] = {}

OBSERVATION_DIR = Path("data/observation")

def record_tick(bot_id: str, status: str):
    """Record a sampled tick status for the observation report."""
    now = time.time()
    # 1-in-60 sampling (approx 1 sample per minute if ticks are 1s)
    if now - _LAST_SAMPLE.get(bot_id, 0) < 60:
        return
    
    _LAST_SAMPLE[bot_id] = now
    
    if bot_id not in _TICK_LOGS:
        _TICK_LOGS[bot_id] = deque(maxlen=1440) # 24 hours at 1 sample/min
        # Load existing if any
        _load(bot_id)
        
    _TICK_LOGS[bot_id].append(status)
    _save(bot_id)

def get_histogram(bot_id: str) -> dict[str, int]:
    """Return a status histogram for the last 24h of recorded ticks."""
    if bot_id not in _TICK_LOGS:
        _load(bot_id)
    
    logs = _TICK_LOGS.get(bot_id, [])
    counts = {}
    for status in logs:
        counts[status] = counts.get(status, 0) + 1
    return counts

def get_tick_count(bot_id: str) -> int:
    """Estimated total ticks in last 24h (extrapolated from sampled logs)."""
    if bot_id not in _TICK_LOGS:
        _load(bot_id)
    return len(_TICK_LOGS.get(bot_id, [])) * 60

def _save(bot_id: str):
    OBSERVATION_DIR.mkdir(parents=True, exist_ok=True)
    path = OBSERVATION_DIR / f"{bot_id}.json"
    with open(path, "w") as f:
        json.dump(list(_TICK_LOGS[bot_id]), f)

def _load(bot_id: str):
    path = OBSERVATION_DIR / f"{bot_id}.json"
    if path.exists():
        try:
            with open(path, "r") as f:
                data = json.load(f)
                _TICK_LOGS[bot_id] = deque(data, maxlen=1440)
        except Exception:
            _TICK_LOGS[bot_id] = deque(maxlen=1440)
    else:
        _TICK_LOGS[bot_id] = deque(maxlen=1440)
