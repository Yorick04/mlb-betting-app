import sqlite3
import pandas as pd
import joblib
import numpy as np
from sklearn.model_selection import train_test_split

def run_backtest():
    print("--- ⏪ MLB AI Backtesting Engine ---")
    
    # 1. Load the trained AI models and scaler
    try:
        model_ml = joblib.load('mlb_ml_model.pkl')
        model_ou = joblib.load('mlb_ou_model.pkl')
        scaler = joblib.load('scaler.pkl')
    except FileNotFoundError:
        print("❌ Error: Could not find model or scaler .pkl files.")
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
    
    # Updated to 4.50 baselines to match the rest of the patched pipeline
    fill_values = {
        'temp': 72.0, 'park_factor': 100.0, 'umpire_multiplier': 1.0,
        'home_fatigue': 0.0, 'away_fatigue': 0.0,
        'home_lineup_mult': 1.0, 'away_lineup_mult': 1.0,
        'home_sp_score': 4.50, 'away_sp_score': 4.50,
        'home_bp_score': 4.50, 'away_bp_score': 4.50
    }
    df_clean = df.fillna(value=fill_values)

    # 4. PREVENT DATA LEAKAGE: Split data exactly how we did in training
    _, df_test = train_test_split(df_clean, test_size=0.2, random_state=42)
    df_test = df_test.copy()

    print(f"📊 Backtesting AI on {len(df_test)} UNSEEN historical games (True Backtest)...\n")

    # 5. Scale and Predict
    X_test = df_test[features]
    X_test_scaled = scaler.transform(X_test)
    
    df_test['ai_projected_diff'] = model_ml.predict(X_test_scaled)
    df_test['ai_projected_total'] = model_ou.predict(X_test_scaled)
    
    # Calculate actuals
    df_test['actual_run_diff'] = df_test['actual_home_score'] - df_test['actual_away_score']
    df_test['actual_total'] = df_test['actual_home_score'] + df_test['actual_away_score']

    # --- 6A. Grade Moneyline ---
    df_test['ai_ml_pick'] = np.where(df_test['ai_projected_diff'] > 0, 'HOME', 'AWAY')
    df_test['actual_ml_winner'] = np.where(df_test['actual_run_diff'] > 0, 'HOME', 'AWAY')
    df_test['is_correct_ml'] = df_test['ai_ml_pick'] == df_test['actual_ml_winner']

    hc_ml_bets = df_test[df_test['ai_projected_diff'].abs() >= 1.5]

    # --- 6B. Grade Over/Under ---
    # Convert ou_total to float and drop N/As so we only grade games with historical odds
    df_test['ou_total_float'] = pd.to_numeric(df_test['ou_total'], errors='coerce')
    valid_ou_games = df_test.dropna(subset=['ou_total_float']).copy()
    
    # AI pick logic: if ai_total > ou_total -> OVER, else UNDER
    valid_ou_games['ai_ou_pick'] = np.where(valid_ou_games['ai_projected_total'] > valid_ou_games['ou_total_float'], 'OVER', 'UNDER')
    valid_ou_games['actual_ou_winner'] = np.where(valid_ou_games['actual_total'] > valid_ou_games['ou_total_float'], 'OVER', 'UNDER')
    
    # Handle pushes (drop them so they don't count as losses)
    valid_ou_games = valid_ou_games[valid_ou_games['actual_total'] != valid_ou_games['ou_total_float']]
    valid_ou_games['is_correct_ou'] = valid_ou_games['ai_ou_pick'] == valid_ou_games['actual_ou_winner']
    
    # Edge calculation for high confidence
    valid_ou_games['ou_edge'] = abs(valid_ou_games['ai_projected_total'] - valid_ou_games['ou_total_float'])
    hc_ou_bets = valid_ou_games[valid_ou_games['ou_edge'] >= 1.25]

    # --- Output ML Results ---
    print("="*50)
    print("📈 TRUE BACKTEST RESULTS (MONEYLINE)")
    print("="*50)
    
    total_ml = len(df_test)
    overall_wins_ml = df_test['is_correct_ml'].sum()
    print(f"Overall Accuracy (Betting Every Game):")
    print(f"Games: {total_ml} | Wins: {overall_wins_ml} | Win %: {(overall_wins_ml / total_ml) * 100:.1f}%\n")
    
    hc_games_ml = len(hc_ml_bets)
    hc_wins_ml = hc_ml_bets['is_correct_ml'].sum()
    hc_pct_ml = (hc_wins_ml / hc_games_ml) * 100 if hc_games_ml > 0 else 0
    print(f"High Confidence Accuracy (Projected margin >= 1.5 runs):")
    print(f"Games: {hc_games_ml} | Wins: {hc_wins_ml} | Win %: {hc_pct_ml:.1f}%")
    
    if hc_pct_ml > 52.4:
        print("\n🔥 PROFITABLE ML SYSTEM DETECTED! (Vegas ML breakeven is ~52.4%)")
    else:
        print("\n⚠️ ML System is not beating Vegas breakeven yet.")

    # --- Output OU Results ---
    print("\n" + "="*50)
    print("📈 TRUE BACKTEST RESULTS (OVER/UNDER)")
    print("="*50)
    
    total_ou = len(valid_ou_games)
    if total_ou > 0:
        overall_wins_ou = valid_ou_games['is_correct_ou'].sum()
        print(f"Overall Accuracy (Betting Every Game):")
        print(f"Games: {total_ou} | Wins: {overall_wins_ou} | Win %: {(overall_wins_ou / total_ou) * 100:.1f}%\n")
        
        hc_games_ou = len(hc_ou_bets)
        hc_wins_ou = hc_ou_bets['is_correct_ou'].sum()
        hc_pct_ou = (hc_wins_ou / hc_games_ou) * 100 if hc_games_ou > 0 else 0
        print(f"High Confidence Accuracy (Projected edge >= 1.25 runs):")
        print(f"Games: {hc_games_ou} | Wins: {hc_wins_ou} | Win %: {hc_pct_ou:.1f}%")
        
        if hc_pct_ou > 52.4:
            print("\n🔥 PROFITABLE TOTALS SYSTEM DETECTED! (Vegas -110 breakeven is 52.4%)")
        else:
            print("\n⚠️ Totals System is not beating Vegas breakeven yet.")
    else:
        print("Not enough historical Vegas line data to backtest Totals yet.")
        
    print("="*50)

if __name__ == "__main__":
    run_backtest()