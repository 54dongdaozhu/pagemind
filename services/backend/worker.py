import logging
import socket
import threading
import time

from redis import Redis
from rq import Queue, Worker

from app.core.config import REDIS_URL, RQ_QUEUE_NAME, validate_settings
from app.core.database import init_db
from app.modules.auth.service import ensure_builtin_user
from app.shared import db_log
from app.shared.cache import get_redis


logger = logging.getLogger(__name__)


def _reset_child_connections() -> None:
    """RQ forks per job; inherited sockets can corrupt psycopg/Redis protocol state."""
    from app.core.database import engine
    from app.shared.cache import get_redis

    engine.dispose(close=False)
    get_redis.cache_clear()


class DatabaseSafeWorker(Worker):
    def main_work_horse(self, job, queue):
        _reset_child_connections()
        super().main_work_horse(job, queue)


def _run_db_log_stream_consumer() -> None:
    redis_conn = get_redis()
    consumer_name = f"{socket.gethostname()}:{threading.get_ident()}"
    try:
        redis_conn.xgroup_create(
            db_log.LOG_STREAM_NAME,
            db_log.LOG_CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            logger.exception("Failed to create db_log stream group: %s", exc)

    while True:
        try:
            messages = redis_conn.xreadgroup(
                db_log.LOG_CONSUMER_GROUP,
                consumer_name,
                {db_log.LOG_STREAM_NAME: ">"},
                count=50,
                block=5000,
            )
            for _, entries in messages:
                for message_id, fields in entries:
                    try:
                        kind = fields.get("kind")
                        payload = db_log.json_loads(fields.get("payload") or "{}")
                        db_log.process_stream_entry(kind, payload)
                        redis_conn.xack(db_log.LOG_STREAM_NAME, db_log.LOG_CONSUMER_GROUP, message_id)
                    except Exception:
                        logger.exception("Failed to process db_log stream entry %s", message_id)
        except Exception:
            logger.exception("db_log stream consumer loop failed")
            time.sleep(5)


def main() -> None:
    validate_settings()
    init_db()
    ensure_builtin_user()

    threading.Thread(target=_run_db_log_stream_consumer, name="db_log_stream", daemon=True).start()

    redis_conn = Redis.from_url(REDIS_URL)
    queue = Queue(RQ_QUEUE_NAME, connection=redis_conn)
    worker = DatabaseSafeWorker([queue], connection=redis_conn)
    worker.work()


if __name__ == "__main__":
    main()
