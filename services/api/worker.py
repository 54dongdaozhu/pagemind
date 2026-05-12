from redis import Redis
from rq import Queue, Worker

from app.core.config import REDIS_URL, RQ_QUEUE_NAME, validate_settings
from app.core.database import init_db
from app.services.auth_service import ensure_builtin_user


def main() -> None:
    validate_settings()
    init_db()
    ensure_builtin_user()

    redis_conn = Redis.from_url(REDIS_URL)
    queue = Queue(RQ_QUEUE_NAME, connection=redis_conn)
    worker = Worker([queue], connection=redis_conn)
    worker.work()


if __name__ == "__main__":
    main()
