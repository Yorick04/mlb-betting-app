import sqlite3
import pandas as pd
import joblib
from datetime import datetime
import pytz

def run_daily_predictions():
    print("--- 🤖 MLB AI Daily Predictor ---")
    
    # 1. Load the trained AI model and scaler
    try:
        model = joblib.load('mlb_model.pkl')
        scaler = joblib.load('scaler.pkl')
        print("✅ Successfully loaded AI Model and Scaler.")
    except FileNotFoundError:
        print("❌ Error: Could not find 'mlb_model.pkl' or 'scaler.pkl'.")
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
    
    # Impute missing values with the exact same baselines used in training
    fill_values = {
        'temp': 72.0, 
        'park_factor': 100.0, 
        'umpire_multiplier': 1.0,
        'home_fatigue': 0.0, 
        'away_fatigue': 0.0,
        'home_lineup_mult': 1.0, 
        'away_lineup_mult': 1.0,
        'home_sp_score': 4.50, 
        'away_sp_score': 4.50,
        'home_bp_score': 4.50, 
        'away_bp_score': 4.50
    }
    
    # Apply fill values and isolate the features
    df_features = df[features].fillna(value=fill_values)

    # 4. Scale and Predict
    X_scaled = scaler.transform(df_features)
    predictions = model.predict(X_scaled)
    
    # Add predictions back to the dataframe
    df['ai_projected_diff'] = predictions

    # 5. Display the results
    print("="*50)
    print("🏟️ TODAY'S AI PREDICTIONS (Run Differential)")
    print("Positive Diff = Home Team Favored | Negative Diff = Away Team Favored")
    print("="*50)

    # Sort by the most lopsided games first (highest absolute run diff)
    df_sorted = df.reindex(df['ai_projected_diff'].abs().sort_values(ascending=False).index)

    for index, row in df_sorted.iterrows():
        matchup = f"{row['away_team']} @ {row['home_team']}"
        predicted_diff = row['ai_projected_diff']
        
        # Determine who the AI picks
        if predicted_diff > 0:
            pick = f"🏠 HOME ({row['home_team']})"
            margin = predicted_diff
        else:
            pick = f"✈️ AWAY ({row['away_team']})"
            margin = abs(predicted_diff)
            
        # Format the output
        print(f"\n{matchup}")
        print(f"   AI Pick: {pick} by {margin:.2f} runs")
        
        # Compare to the DraftKings Moneyline if we have it
        ml_home = row.get('ml_home', 'N/A')
        ml_away = row.get('ml_away', 'N/A')
        
        if pd.notna(ml_home) and pd.notna(ml_away) and ml_home != 'N/A':
            print(f"   DraftKings ML: {row['home_team']} ({ml_home}) | {row['away_team']} ({ml_away})")
        else:
            print("   DraftKings ML: Odds not pulled yet.")

if __name__ == "__main__":
    run_daily_predictions()