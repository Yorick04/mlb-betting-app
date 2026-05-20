import sqlite3

def add_park_factor_column():
    conn = sqlite3.connect("mlb_historical_data.db")
    cursor = conn.cursor()
    try:
        # This adds the missing column to your existing table
        cursor.execute("ALTER TABLE game_logs ADD COLUMN park_factor REAL")
        conn.commit()
        print("✅ Added 'park_factor' column to existing database.")
    except sqlite3.OperationalError:
        print("Column 'park_factor' already exists (or table not found).")
    finally:
        conn.close()

if __name__ == "__main__":
    add_park_factor_column()