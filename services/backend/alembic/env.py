import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# ── sys.path: 把 services/backend/ 加入，使 `from app.*` 在任意 CWD 下都可用 ───────
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# ── 加载 .env（开发环境；生产环境由 Docker/k8s 注入）──────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(_backend_dir) / ".env")
except ImportError:
    pass

# ── Alembic 配置 ──────────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── 导入 ORM 元数据和数据库 URL ──────────────────────────────────────────
from app.core.database import Base          # noqa: E402
from app.core.config import DATABASE_URL    # noqa: E402

target_metadata = Base.metadata


# ── 离线模式（生成 SQL 脚本，不连接数据库）──────────────────────────────
def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── 在线模式（直接连接数据库执行）──────────────────────────────────────
def run_migrations_online() -> None:
    connectable = create_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
        pool_pre_ping=True,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
