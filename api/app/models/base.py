from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all persisted models.

    No tables defined yet — the persisted entities in SRS §6.2 land in M1/M2.
    """
