import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config

import pgvector.sqlalchemy  # noqa: F401 - registers vector type

# Import models so metadata includes all tables
from app.core.database import Base
from app.models.api_event import ApiEvent  # noqa: F401
from app.models.face_record import FaceRecord  # noqa: F401

target_metadata = Base.metadata

config = context.config

# Override sqlalchemy.url from environment
database_url = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://facededup:changeme@localhost:5432/facededup"
)
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
