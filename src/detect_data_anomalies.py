import sqlite3
import pandas as pd
import os

def find_anomalies():
    # Automatically resolve the root directory path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    db_path = os.path.join(root_dir, "mlb_historical_data.db")
    
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM game_logs", conn)
    conn.close()

    print(f"--- Scanning {len(df)} games for all outliers and anomalies ---")

    # 1. Check for physically impossible temps
    anomalous_temps = df[df['temp'] < 30]
    if not anomalous_temps.empty:
        print(f"\n⚠️ Found {len(anomalous_temps)} games with suspicious temps (<30°F):")
        print(anomalous_temps[['game_date', 'home_team', 'temp']])

    # 2. Check for missing scores in 'FINAL' games
    missing_scores = df[(df['status'] == 'FINAL') & (df['actual_home_score'].isnull())]
    if not missing_scores.empty:
        print(f"\n⚠️ Found {len(missing_scores)} games marked 'FINAL' but missing actual scores:")
        print(missing_scores[['game_date', 'game_id']])

    # 3. Check for absurdly high park factors
    outlier_park = df[df['park_factor'] > 150]
    if not outlier_park.empty:
        print(f"\n⚠️ Found {len(outlier_park)} games with unusually high park factors (>150):")
        print(outlier_park[['game_date', 'home_team', 'park_factor']])

    # 4. New: Check for extreme run totals (e.g., games with > 30 total runs)
    # This helps catch data entry errors where stats might have been combined incorrectly
    df['total_runs'] = df['actual_home_score'] + df['actual_away_score']
    extreme_runs = df[df['total_runs'] > 30]
    if not extreme_runs.empty:
        print(f"\n⚠️ Found {len(extreme_runs)} games with extreme total runs (>30):")
        print(extreme_runs[['game_date', 'home_team', 'away_team', 'total_runs']])

    # 5. New: Check for impossible fatigue values
    # Fatigue should realistically be between 0 and 1.0 based on your bullpen logic
    anomalous_fatigue = df[(df['home_fatigue'] < 0) | (df['away_fatigue'] < 0)]
    if not anomalous_fatigue.empty:
        print(f"\n⚠️ Found {len(anomalous_fatigue)} games with negative fatigue scores:")
        print(anomalous_fatigue[['game_date', 'home_team', 'home_fatigue', 'away_fatigue']])

    print("\n✅ Scan complete.")

if __name__ == "__main__":
    find_anomalies()