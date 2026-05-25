import sqlite3
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error
import xgboost as xgb

def run_totals_laboratory():
    print("🔬 Welcome to the MLB Totals Laboratory")
    print("📥 Fetching historical data...")
    
    conn = sqlite3.connect("mlb_historical_data.db")
    query = "SELECT * FROM game_logs WHERE status = 'FINAL' AND game_date >= '2026-03-01'"
    df = pd.read_sql_query(query, conn)
    conn.close()

    # --- 1. Target Variables ---
    df['total_runs'] = df['actual_home_score'] + df['actual_away_score']
    df['home_runs'] = df['actual_home_score']
    df['away_runs'] = df['actual_away_score']

    # --- 2. Feature Engineering (The Wind Impact) ---
    # Convert text directions ("Out to CF", "In from LF") into a mathematical multiplier
    def calculate_wind_impact(row):
        dir_str = str(row['wind_dir']).lower()
        speed = float(row['wind_speed']) if pd.notna(row['wind_speed']) else 0.0
        
        if 'out' in dir_str:
            return speed * 1.0   # Wind blowing out helps hitting
        elif 'in' in dir_str:
            return speed * -1.0  # Wind blowing in hurts hitting
        else:
            return 0.0           # Crosswinds / Dome

    df['wind_impact'] = df.apply(calculate_wind_impact, axis=1)

    # --- 3. Feature Sets & Imputation ---
    base_features = [
        'home_sp_score', 'away_sp_score', 'home_bp_score', 'away_bp_score', 
        'home_fatigue', 'away_fatigue', 'home_lineup_mult', 'away_lineup_mult', 
        'temp', 'park_factor', 'umpire_multiplier'
    ]
    
    all_features = base_features + ['wind_impact']

    fill_values = {
        'temp': 72.0, 'park_factor': 100.0, 'umpire_multiplier': 1.0,
        'home_fatigue': 0.0, 'away_fatigue': 0.0,
        'home_lineup_mult': 1.0, 'away_lineup_mult': 1.0,
        'wind_impact': 0.0
    }
    
    df = df.fillna(value=fill_values).dropna(subset=['actual_home_score', 'actual_away_score'])

    # --- 4. Prepare the Data Splits ---
    # We use the exact same random_state so every model takes the exact same test!
    X_base = df[base_features]
    X_all = df[all_features]
    
    scaler_base = StandardScaler()
    scaler_all = StandardScaler()
    
    X_base_scaled = scaler_base.fit_transform(X_base)
    X_all_scaled = scaler_all.fit_transform(X_all)

    y_total = df['total_runs']
    y_home = df['home_runs']
    y_away = df['away_runs']

    # Indices split to keep track of rows across different targets
    indices = np.arange(len(df))
    idx_train, idx_test = train_test_split(indices, test_size=0.2, random_state=42)

    results = {}

    print("\n🧪 Running Experiments... (This may take a moment)")

    # =====================================================================
    # BASELINE: Random Forest (Game Totals)
    # =====================================================================
    rf_base = RandomForestRegressor(n_estimators=500, max_depth=6, min_samples_leaf=10, random_state=42, n_jobs=-1)
    rf_base.fit(X_base_scaled[idx_train], y_total.iloc[idx_train])
    preds_baseline = rf_base.predict(X_base_scaled[idx_test])
    results['1. Baseline (RF Game Totals)'] = mean_absolute_error(y_total.iloc[idx_test], preds_baseline)

    # =====================================================================
    # TEST A: Weather (Random Forest + Wind)
    # =====================================================================
    rf_weather = RandomForestRegressor(n_estimators=500, max_depth=6, min_samples_leaf=10, random_state=42, n_jobs=-1)
    rf_weather.fit(X_all_scaled[idx_train], y_total.iloc[idx_train])
    preds_weather = rf_weather.predict(X_all_scaled[idx_test])
    results['2. Feature Upgrade (Added Wind)'] = mean_absolute_error(y_total.iloc[idx_test], preds_weather)

    # =====================================================================
    # TEST B: Algorithm (XGBoost Game Totals)
    # =====================================================================
    xgb_base = xgb.XGBRegressor(objective='reg:squarederror', n_estimators=500, max_depth=4, learning_rate=0.05, random_state=42)
    xgb_base.fit(X_base_scaled[idx_train], y_total.iloc[idx_train])
    preds_xgb = xgb_base.predict(X_base_scaled[idx_test])
    results['3. Algorithm Upgrade (XGBoost)'] = mean_absolute_error(y_total.iloc[idx_test], preds_xgb)

    # =====================================================================
    # TEST C: Split Targets (RF Team Totals)
    # =====================================================================
    rf_home = RandomForestRegressor(n_estimators=500, max_depth=6, min_samples_leaf=10, random_state=42, n_jobs=-1)
    rf_away = RandomForestRegressor(n_estimators=500, max_depth=6, min_samples_leaf=10, random_state=42, n_jobs=-1)
    
    rf_home.fit(X_base_scaled[idx_train], y_home.iloc[idx_train])
    rf_away.fit(X_base_scaled[idx_train], y_away.iloc[idx_train])
    
    preds_split = rf_home.predict(X_base_scaled[idx_test]) + rf_away.predict(X_base_scaled[idx_test])
    results['4. Target Upgrade (Split Team Totals)'] = mean_absolute_error(y_total.iloc[idx_test], preds_split)

    # =====================================================================
    # THE GOD MODEL: All 3 (XGBoost + Wind + Split Targets)
    # =====================================================================
    xgb_home = xgb.XGBRegressor(objective='reg:squarederror', n_estimators=500, max_depth=4, learning_rate=0.05, random_state=42)
    xgb_away = xgb.XGBRegressor(objective='reg:squarederror', n_estimators=500, max_depth=4, learning_rate=0.05, random_state=42)
    
    xgb_home.fit(X_all_scaled[idx_train], y_home.iloc[idx_train])
    xgb_away.fit(X_all_scaled[idx_train], y_away.iloc[idx_train])
    
    preds_god = xgb_home.predict(X_all_scaled[idx_test]) + xgb_away.predict(X_all_scaled[idx_test])
    results['5. The "God Model" (All 3 Upgrades)'] = mean_absolute_error(y_total.iloc[idx_test], preds_god)

    # --- 5. Print the Leaderboard ---
    print("\n🏆 --- TOTALS MODEL LEADERBOARD (Mean Absolute Error) --- 🏆")
    print("Lower is better. Every decimal point counts!\n")
    
    # Sort results by lowest MAE
    sorted_results = sorted(results.items(), key=lambda item: item[1])
    
    for rank, (name, mae) in enumerate(sorted_results, 1):
        if name == '1. Baseline (RF Game Totals)':
            print(f"{rank}. {name:<40} {mae:.3f} runs (Your Starting Point)")
        else:
            diff = results['1. Baseline (RF Game Totals)'] - mae
            sign = "-" if diff > 0 else "+"
            print(f"{rank}. {name:<40} {mae:.3f} runs ({sign}{abs(diff):.3f} vs baseline)")
            
    print("\n=======================================================")

if __name__ == "__main__":
    run_totals_laboratory()