import os
from sqlalchemy import create_engine, text

# URL from docker-compose.yml (using localhost since ports are mapped)
DATABASE_URL = "postgresql://gardarika:SP129sGZFHNC@localhost:5432/gardarika_db"

engine = create_engine(DATABASE_URL)

def cleanup():
    with engine.connect() as conn:
        print("Dropping legacy columns from 'workouts'...")
        try:
            # We use text() and conn.execute() which in SQLAlchemy 2.0+ needs conn.commit() if manually managing
            conn.execute(text("ALTER TABLE workouts DROP COLUMN IF EXISTS idrider;"))
            conn.execute(text("ALTER TABLE workouts DROP COLUMN IF EXISTS idhorse;"))
            print("Successfully dropped legacy columns.")
        except Exception as e:
            print(f"Error dropping columns (maybe they are already gone?): {e}")

        print("Renaming tables to plural forms...")
        tables_to_rename = {
            "user": "users",
            "breed": "breeds",
            "specialization": "specializations"
        }
        for old, new in tables_to_rename.items():
            try:
                # Need to be careful with quotes for reserved words like 'user'
                conn.execute(text(f"ALTER TABLE \"{old}\" RENAME TO \"{new}\";"))
                print(f"Renamed '{old}' to '{new}'")
            except Exception as e:
                print(f"Error renaming '{old}' (maybe already renamed?): {e}")
        
        # Also drop the view if it exists, server.py will recreate it with correct table names
        try:
            conn.execute(text("DROP VIEW IF EXISTS v_dashboard_stats;"))
            print("Dropped view v_dashboard_stats (will be recreated by server.py)")
        except Exception as e:
            print(f"Error dropping view: {e}")

        conn.commit()
    print("Cleanup script finished.")

if __name__ == "__main__":
    cleanup()
