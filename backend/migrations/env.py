from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool, text
from app.config import settings
from app.db import Base
import app.models  # noqa: F401

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=config.get_main_option('sqlalchemy.url') or settings.database_url, target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={'paramstyle':'named'}, compare_type=True)
    with context.begin_transaction(): context.run_migrations()

def run_migrations_online():
    section=config.get_section(config.config_ini_section) or {}
    section['sqlalchemy.url']=config.get_main_option('sqlalchemy.url') or settings.database_url
    connectable=engine_from_config(section,prefix='sqlalchemy.',poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # Existing revision identifiers exceed Alembic's default VARCHAR(32).
        # Preserve every applied ID; widen only the migration bookkeeping field.
        if connection.dialect.name == 'postgresql':
            with connection.begin():
                connection.execute(text('CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(128) NOT NULL PRIMARY KEY)'))
                connection.execute(text('ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)'))
        context.configure(connection=connection,target_metadata=target_metadata,compare_type=True)
        with context.begin_transaction(): context.run_migrations()

if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
