import sqlite3
import pandas as pd
import joblib
import numpy as np
from sklearn.model_selection import train_test_split

def run_backtest():
    print("--- ⏪ MLB AI Backtesting Engine ---")
    
    # 1. Load the trained AI model and scaler
    try:
        model = joblib.load('mlb_model.pkl')
        scaler = joblib.load('scaler.pkl')
    except FileNotFoundError:
        print("❌ Error: Could not find 'mlb_model.pkl' or 'scaler.pkl'.")
        return

    # 2. Fetch completed games from the database
    conn = sqlite3.connect("mlb_historical_data.db")
    
    # We pull FINAL games where we actually have a score to grade against
    query = "SELECT * FROM game_logs WHERE status = 'FINAL' AND actual_home_score IS NOT NULL"
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("❌ No completed games found in the database to backtest.")
        return

    # 3. Prepare the features
    features = [
        'home_sp_score', 'away_sp_score', 
        'home_bp_score', 'away_bp_score', 
        'home_fatigue', 'away_fatigue', 
        'home_lineup_mult', 'away_lineup_mult', 
        'temp', 'park_factor', 'umpire_multiplier'
    ]
    
    fill_values = {
        'temp': 72.0, 'park_factor': 100.0, 'umpire_multiplier': 1.0,
        'home_fatigue': 0.0, 'away_fatigue': 0.0,
        'home_lineup_mult': 1.0, 'away_lineup_mult': 1.0,
        'home_sp_score': 0.0, 'away_sp_score': 0.0,
        'home_bp_score': 0.0, 'away_bp_score': 0.0
    }
    df_clean = df.fillna(value=fill_values)

    # 4. PREVENT DATA LEAKAGE: Split data exactly how we did in training!
    # We use random_state=42 so it splits the exact same way as ai_training_preview.py
    # We ONLY want to grade df_test, which is the 20% of games the AI has NEVER seen.
    _, df_test = train_test_split(df_clean, test_size=0.2, random_state=42)
    
    # Make a copy so pandas doesn't complain about modifying a slice
    df_test = df_test.copy()

    print(f"📊 Backtesting AI on {len(df_test)} UNSEEN historical games (True Backtest)...\n")

    # 5. Scale and Predict on the holdout test set
    X_test = df_test[features]
    X_test_scaled = scaler.transform(X_test)
    df_test['ai_projected_diff'] = model.predict(X_test_scaled)
    
    # Calculate the ACTUAL run differential to grade the AI
    df_test['actual_run_diff'] = df_test['actual_home_score'] - df_test['actual_away_score']

    # 6. Grade the Predictions (Moneyline Winners)
    # If AI predicts > 0, it picked Home. If < 0, it picked Away.
    df_test['ai_pick'] = np.where(df_test['ai_projected_diff'] > 0, 'HOME', 'AWAY')
    df_test['actual_winner'] = np.where(df_test['actual_run_diff'] > 0, 'HOME', 'AWAY')
    
    # It's a win if the AI's pick matches the actual winner
    df_test['is_correct'] = df_test['ai_pick'] == df_test['actual_winner']

    # --- ADVANCED FILTERING: ONLY BET WHEN THE AI HAS AN "EDGE" ---
    # The AI is most accurate when predicting blowouts. Let's see how it performs
    # when it projects a run differential of at least 1.5 runs (high confidence).
    high_confidence_bets = df_test[df_test['ai_projected_diff'].abs() >= 1.5]

    total_games = len(df_test)
    overall_wins = df_test['is_correct'].sum()
    overall_win_pct = (overall_wins / total_games) * 100

    hc_games = len(high_confidence_bets)
    hc_wins = high_confidence_bets['is_correct'].sum()
    hc_win_pct = (hc_wins / hc_games) * 100 if hc_games > 0 else 0

    print("="*50)
    print("📈 TRUE BACKTEST RESULTS (Moneyline Winners)")
    print("="*50)
    
    print(f"Overall Accuracy (Betting Every Game):")
    print(f"Games: {total_games} | Wins: {overall_wins} | Win %: {overall_win_pct:.1f}%\n")
    
    print(f"High Confidence Accuracy (Projected margin >= 1.5 runs):")
    print(f"Games: {hc_games} | Wins: {hc_wins} | Win %: {hc_win_pct:.1f}%")
    
    if hc_win_pct > 52.4:
        print("\n🔥 PROFITABLE SYSTEM DETECTED! (Standard Vegas ML breakeven is ~52.4%)")
    else:
        print("\n⚠️ System is not yet beating the Vegas breakeven threshold. Keep feeding it data!")
        
    print("="*50)

if __name__ == "__main__":
    run_backtest()