import time

from django.core.cache import cache

WINDOW_SECONDS = 1


def try_acquire(endpoint_id, limit_per_second: int, clock=time.time) -> bool:
    """
    Fixed one-second window counted in the shared cache (Redis in production), so the limit holds
    across every worker process and not per process.
    """
    key = f"relay:rate:{endpoint_id}:{int(clock())}"
    cache.add(key, 0, timeout=WINDOW_SECONDS + 1)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=WINDOW_SECONDS + 1)
        count = 1
    return count <= limit_per_second
