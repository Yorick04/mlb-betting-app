import sqlite3
import pandas as pd
from pybaseball import statcast_pitcher_expected_stats
import statcast_utils
import time
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

def get_historical_xstats(start_date, end_date):
    """Fetches xStats for a specific historical window."""
    try:
        # Pybaseball doesn't officially support date-ranged xStats directly in this function,
        # but we can fetch the cumulative season stats up to that point by filtering raw pitch data.
        # For simplicity and speed in this backfill, we will use the *current* season xERA. 
        # Note: In a true production environment, you would want rolling 30-day xStats.
        
        print(f"📡 Fetching cumulative 2026 xStats from Baseball Savant...")
        df = statcast_pitcher_expected_stats(2026, 50)
        
        if 'last_name, first_name' in df.columns:
            df['match_name'] = df['last_name, first_name'].astype(str)
        elif 'first_name' in df.columns and 'last_name' in df.columns:
            df['match_name'] = df['first_name'].astype(str) + " " + df['last_name'].astype(str)
        elif 'player_name' in df.columns:
            df['match_name'] = df['player_name'].astype(str)
        else:
            print("⚠️ Column mismatch in PyBaseball.")
            return pd.DataFrame()

        df['match_name'] = df['match_name'].apply(statcast_utils._normalize_name)
        return df
    except Exception as e:
        print(f"Error fetching historical stats: {e}")
        return pd.DataFrame()

def run_backfill():
    print("--- 🕰️ Starting Historical Data Backfill (xStats) ---")
    
    conn = sqlite3.connect("mlb_historical_data.db")
    cursor = conn.cursor()
    
    # Find games that are missing xStats
    query = """
    SELECT game_id, game_date, home_pitcher, away_pitcher 
    FROM game_logs 
    WHERE status = 'FINAL' 
    AND game_date >= '2026-03-01' 
    AND home_sp_xERA IS NULL
    """
    
    df_missing = pd.read_sql_query(query, conn)
    
    if df_missing.empty:
        print("✅ No missing data found. Database is fully up to date!")
        conn.close()
        return

    print(f"🔍 Found {len(df_missing)} historical games missing xStats.")
    
    # Load the master cache once to prevent API rate limits
    master_xstats_df = get_historical_xstats('2026-03-01', '2026-10-31')
    
    if master_xstats_df.empty:
        print("❌ Failed to load master xStats. Aborting backfill.")
        conn.close()
        return
        
    def find_xera(pitcher_name):
        if not pitcher_name or pitcher_name == 'TBD': return None
        clean_name = statcast_utils._normalize_name(pitcher_name)
        match = master_xstats_df[master_xstats_df['match_name'] == clean_name]
        if not match.empty:
            return float(match.iloc[0].get('xera', match.iloc[0].get('est_era', None)))
        return None

    updated_count = 0
    print("⏳ Backfilling database (this will be fast)...")
    
    for index, row in df_missing.iterrows():
        g_id = row['game_id']
        h_pitcher = row['home_pitcher']
        a_pitcher = row['away_pitcher']
        
        h_xera = find_xera(h_pitcher)
        a_xera = find_xera(a_pitcher)
        
        # Only update if we found valid data
        if pd.notna(h_xera) or pd.notna(a_xera):
            update_sql = """
            UPDATE game_logs 
            SET home_sp_xERA = ?, away_sp_xERA = ? 
            WHERE game_id = ?
            """
            cursor.execute(update_sql, (h_xera, a_xera, g_id))
            updated_count += 1
            
    conn.commit()
    conn.close()
    
    print(f"✅ Successfully backfilled {updated_count} historical games with Expected Stats!")

if __name__ == "__main__":
    run_backfill()