"""
Database client module.

Provides a reusable Prisma client instance and lifecycle helpers
for FastAPI integration.

Usage:
    from app.database import db, connect_db, disconnect_db
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from prisma import Prisma

# Singleton Prisma client instance shared across the application.
db = Prisma()


async def connect_db() -> None:
    """Open the database connection pool.

    Called once during application startup.  All subsequent queries
    reuse this single connection pool.
    """
    if not db.is_connected():
        await db.connect()


async def disconnect_db() -> None:
    """Close the database connection pool.

    Called once during application shutdown to release resources.
    """
    if db.is_connected():
        await db.disconnect()


async def get_db() -> AsyncGenerator[Prisma, None]:
    """FastAPI dependency that yields the active Prisma client.

    Use with ``Depends`` in route handlers:

        @router.get("/")
        async def handler(db: Prisma = Depends(get_db)):
            ...
    """
    if not db.is_connected():
        await db.connect()
    try:
        yield db
    except Exception as exc:
        if "Closed" in str(exc) or "connection" in str(exc).lower():
            try:
                if db.is_connected():
                    await db.disconnect()
                await db.connect()
            except Exception:
                pass
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[override]
    """Application lifespan context manager.

    Connects to the database on startup and disconnects on shutdown.
    Registered via ``FastAPI(lifespan=lifespan)`` in ``main.py``.
    """
    # --- startup ---
    await connect_db()
    yield
    # --- shutdown ---
    await disconnect_db()
