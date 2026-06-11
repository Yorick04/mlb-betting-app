import sqlite3
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score
import xgboost as xgb
import joblib
import os

def train_mybaseball_pal_ai():
    print("📥 Fetching historical data from SQLite...")
    
    # Automatically resolve the root directory path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    db_path = os.path.join(root_dir, "mlb_historical_data.db")
    
    conn = sqlite3.connect(db_path)
    
    # Filter for fresh 2026 data
    query = "SELECT * FROM game_logs WHERE status = 'FINAL' AND game_date >= '2026-03-01'"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if len(df) < 500:
        print(f"❌ Not enough data. You have {len(df)} games; you need at least 500.")
        return
        
    print(f"✅ Loaded {len(df)} games.")

    # 2. Advanced Feature Engineering
    df['run_diff'] = df['actual_home_score'] - df['actual_away_score'] 
    df['home_runs'] = df['actual_home_score']
    df['away_runs'] = df['actual_away_score']
    
    def calculate_wind_impact(row):
        dir_str = str(row['wind_dir']).lower()
        speed = float(row['wind_speed']) if pd.notna(row['wind_speed']) else 0.0
        if 'out' in dir_str: return speed * 1.0
        elif 'in' in dir_str: return speed * -1.0
        else: return 0.0
        
    df['wind_impact'] = df.apply(calculate_wind_impact, axis=1)
    
    features = [
        'home_sp_score', 'away_sp_score', 
        'home_bp_score', 'away_bp_score', 
        'home_fatigue', 'away_fatigue', 
        'home_lineup_mult', 'away_lineup_mult', 
        'temp', 'park_factor', 'umpire_multiplier', 'wind_impact'
    ]
    
    fill_values = {
        'home_sp_score': 4.50, 'away_sp_score': 4.50,
        'home_bp_score': 4.50, 'away_bp_score': 4.50,
        'temp': 72.0, 'park_factor': 100.0, 'umpire_multiplier': 1.0,
        'home_fatigue': 0.0, 'away_fatigue': 0.0,
        'home_lineup_mult': 1.0, 'away_lineup_mult': 1.0,
        'wind_impact': 0.0
    }
    
    df = df.fillna(value=fill_values)
    df = df.dropna(subset=['actual_home_score', 'actual_away_score'])
    
    print(f"✅ Data Sanitized: {len(df)} games ready for training.\n")

    X = df[features]
    y_ml = df['run_diff']
    y_home = df['home_runs']
    y_away = df['away_runs']

    # 3. Scale Features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # 4. Train Model 1: Moneyline (Run Differential - Random Forest)
    print("🤖 Training Model 1: Moneyline / Run Differential (RF)...")
    model_ml = RandomForestRegressor(n_estimators=500, max_depth=5, min_samples_leaf=10, random_state=42, n_jobs=-1)
    model_ml.fit(X_scaled, y_ml)

    # 5. Train Model 2 & 3: Totals (Split Targets - XGBoost)
    print("🤖 Training Model 2: Home Runs (XGBoost)...")
    model_home = xgb.XGBRegressor(objective='reg:squarederror', n_estimators=500, max_depth=4, learning_rate=0.05, random_state=42)
    model_home.fit(X_scaled, y_home)
    
    print("🤖 Training Model 3: Away Runs (XGBoost)...")
    model_away = xgb.XGBRegressor(objective='reg:squarederror', n_estimators=500, max_depth=4, learning_rate=0.05, random_state=42)
    model_away.fit(X_scaled, y_away)

    # 6. Save the Suite (Dynamically pointing to the root directory)
    print("💾 Saving the Ballpark Pal Suite...")
    joblib.dump(model_ml, os.path.join(root_dir, 'mlb_ml_model.pkl'))
    joblib.dump(model_home, os.path.join(root_dir, 'mlb_home_model.pkl'))
    joblib.dump(model_away, os.path.join(root_dir, 'mlb_away_model.pkl'))
    joblib.dump(scaler, os.path.join(root_dir, 'scaler.pkl'))
    print("✅ Successfully saved models and scaler.")

if __name__ == "__main__":
    train_mybaseball_pal_ai()