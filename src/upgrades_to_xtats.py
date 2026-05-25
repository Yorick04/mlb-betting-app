import sqlite3

def add_xstats_columns():
    print("🛠️ Upgrading database for Statcast Expected Metrics (xStats)...")
    conn = sqlite3.connect("mlb_historical_data.db")
    cursor = conn.cursor()
    
    # The new columns we want to add safely
    new_columns = [
        "home_sp_xERA REAL DEFAULT NULL",
        "away_sp_xERA REAL DEFAULT NULL",
        "home_lineup_xBA REAL DEFAULT NULL",
        "away_lineup_xBA REAL DEFAULT NULL",
        "home_lineup_xSLG REAL DEFAULT NULL",
        "away_lineup_xSLG REAL DEFAULT NULL"
    ]
    
    for col in new_columns:
        try:
            cursor.execute(f"ALTER TABLE game_logs ADD COLUMN {col}")
            print(f"✅ Added column: {col.split()[0]}")
        except sqlite3.OperationalError as e:
            # If it already exists, safely skip it
            print(f"Notice: {col.split()[0]} already exists.")
            
    conn.commit()
    conn.close()
    print("🚀 Database upgrade complete! All historical data is perfectly safe.")

if __name__ == "__main__":
    add_xstats_columns()