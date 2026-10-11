"""Database package.

Re-exports the Prisma client instance and lifecycle helpers so they
can be imported from any module with a single statement:

    from app.database import db, connect_db, disconnect_db, get_db
"""

from app.database.client import connect_db, db, disconnect_db, get_db, lifespan

__all__ = ["db", "connect_db", "disconnect_db", "get_db", "lifespan"]
