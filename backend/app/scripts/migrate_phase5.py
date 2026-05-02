"""
Database migration script — adds new columns and tables for Phase 5 (Libraries).

Run once: python -m app.scripts.migrate_phase5

What it does:
1. Create 'libraries' and 'library_sources' tables
2. Add new columns to 'films' table: library_id, path, video_path, poster_path, has_existing_subs
"""

import asyncio
import sqlite3
import os
import sys


DB_PATH = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/subtitle_translator.db")
# Extract plain path from SQLAlchemy URL
if ":///" in DB_PATH:
    DB_PATH = DB_PATH.split(":///")[-1]
else:
    DB_PATH = "./data/subtitle_translator.db"


def migrate():
    print(f"🔧 Migrating database: {DB_PATH}")

    if not os.path.exists(DB_PATH):
        print(f"⚠️  Database file not found at {DB_PATH}, creating new one")
        # The app will create it on first boot
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Create libraries table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS libraries (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✅ libraries table ready")

    # 2. Create library_sources table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS library_sources (
            id TEXT PRIMARY KEY,
            library_id TEXT NOT NULL REFERENCES libraries(id),
            source_type TEXT DEFAULT 'local',
            path TEXT NOT NULL,
            ssh_host TEXT,
            ssh_port INTEGER DEFAULT 22,
            ssh_username TEXT,
            ssh_auth_type TEXT,
            ssh_private_key_path TEXT,
            ssh_password TEXT,
            ssh_remote_path TEXT,
            enabled INTEGER DEFAULT 1,
            scan_depth INTEGER DEFAULT 2,
            last_scan_at DATETIME,
            scan_status TEXT DEFAULT 'idle',
            scan_error TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✅ library_sources table ready")

    # 3. Add new columns to films table (if not exist)
    new_columns = {
        "library_id": "TEXT REFERENCES libraries(id)",
        "path": "TEXT",
        "video_path": "TEXT",
        "poster_path": "TEXT",
        "has_existing_subs": "INTEGER DEFAULT 0",
    }

    # Get existing columns
    cursor.execute("PRAGMA table_info(films)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    for col_name, col_type in new_columns.items():
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE films ADD COLUMN {col_name} {col_type}")
                print(f"✅ Added column films.{col_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    print(f"⏭️  Column films.{col_name} already exists")
                else:
                    print(f"❌ Error adding films.{col_name}: {e}")
        else:
            print(f"⏭️  Column films.{col_name} already exists")

    # 4. Done

    conn.commit()
    conn.close()

    print("\n🎉 Migration complete!")


if __name__ == "__main__":
    migrate()