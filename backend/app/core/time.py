from datetime import datetime, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_epoch_ms() -> int:
    return int(now_utc().timestamp() * 1000)
