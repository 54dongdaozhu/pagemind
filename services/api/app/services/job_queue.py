import logging
from functools import lru_cache
from typing import Any

from app.core.config import REDIS_URL, RQ_JOB_TIMEOUT_SECONDS, RQ_QUEUE_NAME


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_queue():
    from redis import Redis
    from rq import Queue

    redis_conn = Redis.from_url(REDIS_URL)
    return Queue(RQ_QUEUE_NAME, connection=redis_conn)


def enqueue_job(func: Any, *args: Any, **kwargs: Any) -> bool:
    try:
        from rq import Retry

        queue = _get_queue()
        queue.enqueue(
            func,
            *args,
            **kwargs,
            job_timeout=RQ_JOB_TIMEOUT_SECONDS,
            retry=Retry(max=3, interval=[10, 30, 60]),
            result_ttl=0,
            failure_ttl=86400,
        )
        return True
    except ImportError as e:
        logger.warning("RQ dependencies are not installed; falling back to synchronous persistence: %s", e)
    except Exception as e:
        logger.exception("Failed to enqueue RQ job; falling back to synchronous persistence: %s", e)
    return False
