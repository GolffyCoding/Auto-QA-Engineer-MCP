"""Seeds checkout.db with a users/orders schema that has one INTENTIONAL
orphaned foreign key row (orders.user_id = 999, which has no matching
users.id), so db.check_fk_integrity has a real broken reference to find.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "checkout.db"


def seed():
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, total REAL);

        INSERT INTO users (id, email) VALUES (1, 'alice@example.com'), (2, 'bob@example.com');
        INSERT INTO orders (id, user_id, total) VALUES
            (1, 1, 100.0),
            (2, 2, 50.0),
            (3, 999, 80.0);  -- orphaned: user 999 does not exist
        """
    )
    conn.commit()
    conn.close()
    print(f"seeded {DB_PATH}")


if __name__ == "__main__":
    seed()
