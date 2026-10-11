#!/usr/bin/env python3
"""Create an ADMIN user, or promote an existing user to ADMIN.

Usage (inside the backend container or venv):
    python scripts/create_admin.py --email you@example.com --username admin
Password is read from the ADMIN_PASSWORD env var, or prompted for.
"""
import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prisma import Prisma  # noqa: E402

from app.core.security import hash_password  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description="Create or promote an admin user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--username", required=True)
    args = parser.parse_args()

    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
    if len(password) < 12:
        print("Password must be at least 12 characters.", file=sys.stderr)
        return 1

    db = Prisma()
    await db.connect()
    try:
        existing = await db.user.find_unique(where={"email": args.email.lower()})
        if existing:
            await db.user.update(where={"id": existing.id}, data={"role": "ADMIN"})
            print(f"Promoted existing user {existing.email} to ADMIN.")
        else:
            await db.user.create(
                data={
                    "email": args.email.lower(),
                    "username": args.username,
                    "hashedPassword": hash_password(password),
                    "role": "ADMIN",
                }
            )
            print(f"Created ADMIN user {args.email}.")
    finally:
        await db.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
