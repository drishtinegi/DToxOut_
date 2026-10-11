import asyncio
from prisma import Prisma


async def main():
    db = Prisma()
    await db.connect()

    users = await db.user.find_many()

    print("\nREGISTERED USERS:\n")

    for user in users:
        print(f"ID:       {user.id}")
        print(f"Email:    {user.email}")
        print(f"Username: {user.username}")
        print(f"Role:     {user.role}")
        print(f"Created:  {user.createdAt}")
        print("-" * 50)

    await db.disconnect()


asyncio.run(main())