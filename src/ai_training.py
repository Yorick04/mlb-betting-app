import sqlite3
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score
import joblib

def train_mybaseball_pal_ai():
    print("📥 Fetching historical data from SQLite...")
    conn = sqlite3.connect("mlb_historical_data.db")
    
    # Filter for fresh 2026 data
    query = "SELECT * FROM game_logs WHERE status = 'FINAL' AND game_date >= '2026-03-01'"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if len(df) < 500:
        print(f"❌ Not enough data. You have {len(df)} games; you need at least 500.")
        return
        
    print(f"✅ Loaded {len(df)} games.")

    # 2. Advanced Feature Engineering (TWO TARGETS)
    df['run_diff'] = df['actual_home_score'] - df['actual_away_score'] # Target 1: Moneyline
    df['total_runs'] = df['actual_home_score'] + df['actual_away_score'] # Target 2: Over/Under
    
    features = [
        'home_sp_score', 'away_sp_score', 
        'home_bp_score', 'away_bp_score', 
        'home_fatigue', 'away_fatigue', 
        'home_lineup_mult', 'away_lineup_mult', 
        'temp', 'park_factor', 'umpire_multiplier'
    ]
    
    # --- FIX: Added SP and BP scores to prevent scaler from crashing on TBD games ---
    fill_values = {
        'home_sp_score': 4.50, 'away_sp_score': 4.50,
        'home_bp_score': 4.50, 'away_bp_score': 4.50,
        'temp': 72.0, 'park_factor': 100.0, 'umpire_multiplier': 1.0,
        'home_fatigue': 0.0, 'away_fatigue': 0.0,
        'home_lineup_mult': 1.0, 'away_lineup_mult': 1.0
    }
    
    df = df.fillna(value=fill_values)
    df = df.dropna(subset=['actual_home_score', 'actual_away_score'])
    
    print(f"✅ Data Sanitized: {len(df)} games ready for training.\n")

    X = df[features]
    y_ml = df['run_diff']
    y_ou = df['total_runs']

    # 3. Scale Features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # 4. Train Model 1: Moneyline (Run Differential)
    print("🤖 Training Model 1: Moneyline / Run Differential...")
    X_train_ml, X_test_ml, y_train_ml, y_test_ml = train_test_split(X_scaled, y_ml, test_size=0.2, random_state=42)
    
    model_ml = RandomForestRegressor(n_estimators=500, max_depth=5, min_samples_leaf=10, random_state=42, n_jobs=-1)
    model_ml.fit(X_train_ml, y_train_ml)
    
    preds_ml = model_ml.predict(X_test_ml)
    correct_ml_picks = sum((preds_ml > 0) == (y_test_ml > 0))
    ml_accuracy = (correct_ml_picks / len(y_test_ml)) * 100
    
    print(f"   -> Implied ML Accuracy: {ml_accuracy:.1f}%\n")

    # 5. Train Model 2: Over/Under (Total Runs)
    print("🤖 Training Model 2: Over/Under (Total Runs)...")
    X_train_ou, X_test_ou, y_train_ou, y_test_ou = train_test_split(X_scaled, y_ou, test_size=0.2, random_state=42)
    
    # Slightly deeper tree for totals to capture combined weather/umpire nuances
    model_ou = RandomForestRegressor(n_estimators=500, max_depth=6, min_samples_leaf=10, random_state=42, n_jobs=-1)
    model_ou.fit(X_train_ou, y_train_ou)
    
    preds_ou = model_ou.predict(X_test_ou)
    mae_ou = mean_absolute_error(y_test_ou, preds_ou)
    
    print(f"   -> Mean Absolute Error: {mae_ou:.2f} runs\n")

    # 6. Save the Suite
    print("💾 Saving the Ballpark Pal Suite...")
    joblib.dump(model_ml, 'mlb_ml_model.pkl')
    joblib.dump(model_ou, 'mlb_ou_model.pkl')
    joblib.dump(scaler, 'scaler.pkl')
    print("✅ Successfully saved: mlb_ml_model.pkl, mlb_ou_model.pkl, scaler.pkl")

if __name__ == "__main__":
    train_mybaseball_pal_ai()