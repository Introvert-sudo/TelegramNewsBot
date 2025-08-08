import asyncio
from app.data import db

async def add_source():
    url = input("Enter the source URL to add: ").strip()
    name = input("Enter the source name: ").strip()
    source_id = await db.add_source(name, url)
    if source_id:
        print(f"Source added with ID: {source_id}")
    else:
        print("Failed to add source.")

async def delete_source():
    sources = await db.get_all_sources()
    if not sources:
        print("No sources found.")
        return
    print("Available sources:")
    for s in sources:
        print(f"{s['id']}: {s['name']} ({s['url']})")
    try:
        source_id = int(input("Enter the ID of the source to delete: ").strip())
    except ValueError:
        print("Invalid ID.")
        return
    await db.delete_source(source_id)

async def main():
    print("Admin Source Management")
    print("1. Add source")
    print("2. Delete source")
    choice = input("Choose an option (1/2): ").strip()
    if choice == "1":
        await add_source()
    elif choice == "2":
        await delete_source()
    else:
        print("Invalid choice.")

if __name__ == "__main__":
    asyncio.run(main())