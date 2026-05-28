import sqlite3
import pandas as pd
import joblib
from datetime import datetime
import pytz

def run_daily_predictions():
    print("--- 🤖 MLB AI Daily Predictor ---")
    
    # 1. Load BOTH trained AI models and the scaler
    try:
        model_ml = joblib.load('mlb_ml_model.pkl')
        model_ou = joblib.load('mlb_ou_model.pkl')
        scaler = joblib.load('scaler.pkl')
        print("✅ Successfully loaded ML Model, OU Model, and Scaler.")
    except FileNotFoundError:
        print("❌ Error: Could not find the required .pkl files.")
        print("Make sure you have run your ai_training.py script first!")
        return

    # 2. Fetch today's pending games from the database
    conn = sqlite3.connect("mlb_historical_data.db")
    
    # We only want games that haven't been graded 'FINAL' yet
    query = "SELECT * FROM game_logs WHERE status = 'PENDING'"
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("\n⚾ No pending games found in the database.")
        print("Make sure you run your daily scraper first so the AI has games to predict!")
        return

    print(f"🔍 Analyzing {len(df)} upcoming games...\n")

    # 3. Prepare the features EXACTLY as we did during training
    features = [
        'home_sp_score', 'away_sp_score', 
        'home_bp_score', 'away_bp_score', 
        'home_fatigue', 'away_fatigue', 
        'home_lineup_mult', 'away_lineup_mult', 
        'temp', 'park_factor', 'umpire_multiplier'
    ]
    
    # Handle missing values to prevent scaler crashes
    df[features] = df[features].fillna(df[features].mean())
    
    X = df[features]
    X_scaled = scaler.transform(X)

    # 4. Generate Predictions for BOTH targets
    df['ai_projected_diff'] = model_ml.predict(X_scaled)
    df['ai_projected_total'] = model_ou.predict(X_scaled)

    # 5. Display the results
    print("="*65)
    print("🏟️ TODAY'S AI PREDICTIONS (Moneyline & Totals)")
    print("Positive ML = Home Team Favored | Negative ML = Away Team Favored")
    print("="*65)

    # Sort by the most lopsided games first (highest absolute run diff)
    df_sorted = df.reindex(df['ai_projected_diff'].abs().sort_values(ascending=False).index)

    for index, row in df_sorted.iterrows():
        matchup = f"{row['away_team']} @ {row['home_team']}"
        predicted_diff = row['ai_projected_diff']
        predicted_total = row['ai_projected_total']
        
        # Determine who the AI picks for Moneyline
        if predicted_diff > 0:
            pick = f"🏠 HOME ({row['home_team']})"
            margin = predicted_diff
        else:
            pick = f"✈️ AWAY ({row['away_team']})"
            margin = abs(predicted_diff)
            
        # Format the output
        print(f"\n{matchup}")
        print(f"   ML Pick: {pick} by {margin:.2f} runs")
        print(f"   OU Pick: Projected Total Runs: {predicted_total:.2f}")
        
        # Compare to the DraftKings odds if we have them
        ml_home = row.get('ml_home', 'N/A')
        ml_away = row.get('ml_away', 'N/A')
        ou_total = row.get('ou_total', 'N/A')
        spread = row.get('spread', 'N/A')
        
        print(f"   Odds   : ML (H: {ml_home} | A: {ml_away}) | O/U: {ou_total} | Spread: {spread}")

if __name__ == "__main__":
    run_daily_predictions()