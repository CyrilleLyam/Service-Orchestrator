from __future__ import annotations

from typing import Any, Self

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from service_orchestrator.shared.domain.exceptions import ConcurrentModification

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_db_engine(url: str, **kwargs: Any) -> Engine:
    return create_engine(url, pool_pre_ping=True, **kwargs)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False, autoflush=False)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Unit of work used outside its `with` block")
        return self._session

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self._bind_repositories(self._session)
        return self

    def __exit__(self, exc_type: object, exc: BaseException | None, tb: object) -> None:
        session, self._session = self.session, None
        try:
            session.rollback()
        finally:
            session.close()
        if isinstance(exc, IntegrityError):
            raise ConcurrentModification() from exc

    def commit(self) -> None:
        self.session.commit()

    def _bind_repositories(self, session: Session) -> None:
        raise NotImplementedError
