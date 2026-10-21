from __future__ import annotations

import argparse
import logging
from pathlib import Path

from sqlalchemy import Engine

from service_orchestrator.config import Settings
from service_orchestrator.shared.infrastructure.database import create_db_engine
from service_orchestrator.shared.infrastructure.log_config import configure_logging

logger = logging.getLogger(__name__)

DEFAULT_SEED = Path("seeds") / "services.sql"


def apply_sql(engine: Engine, path: Path) -> None:
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        cursor = connection.connection.cursor()
        try:
            cursor.execute(path.read_text())
        finally:
            cursor.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Apply SQL seed files to DATABASE_URL.")
    parser.add_argument("files", nargs="*", type=Path, default=[DEFAULT_SEED])
    args = parser.parse_args(argv)

    settings = Settings()
    configure_logging(settings.log_level, settings.log_format, settings.log_sql)
    engine = create_db_engine(settings.database_url)
    try:
        for path in args.files:
            apply_sql(engine, path)
            logger.info("seed applied", extra={"file": str(path)})
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
