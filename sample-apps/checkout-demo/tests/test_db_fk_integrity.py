"""Database integrity check using qa_mcp's own DatabaseAnalyzer (the same
code report.generate would classify a failure from) against checkout.db
(seeded by seed_db.py). EXPECTED TO FAIL - orders.user_id=999 has no
matching row in users, an orphaned foreign key seeded on purpose.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root, for `import qa_mcp`

from qa_mcp.analyzers.database_analyzer import DatabaseAnalyzer

DB_PATH = Path(__file__).parent.parent / "checkout.db"


async def main():
    analyzer = DatabaseAnalyzer(f"sqlite:///{DB_PATH}")
    result = await analyzer.check_fk_integrity("orders", "user_id", "users", "id")

    if result["status"] != "ok":
        print(
            f"foreign key constraint violation: {result['invalid_references']} row(s) in "
            f"orders.user_id have no matching users.id",
            file=sys.stderr,
        )
        sys.exit(1)

    print("OK: no orphaned foreign keys")


if __name__ == "__main__":
    asyncio.run(main())
