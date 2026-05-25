import sqlite3
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score

def run_xstats_laboratory():
    print("🔬 Welcome to the MLB xStats Laboratory")
    print("📥 Fetching backfilled historical data...")
    
    conn = sqlite3.connect("mlb_historical_data.db")
    query = "SELECT * FROM game_logs WHERE status = 'FINAL' AND game_date >= '2026-03-01'"
    df = pd.read_sql_query(query, conn)
    conn.close()

    # Calculate Run Differential (Target Variable)
    df['run_diff'] = df['actual_home_score'] - df['actual_away_score']

    # --- Feature Sets ---
    base_features = [
        'home_sp_score', 'away_sp_score', 'home_bp_score', 'away_bp_score', 
        'home_fatigue', 'away_fatigue', 'home_lineup_mult', 'away_lineup_mult', 
        'temp', 'park_factor', 'umpire_multiplier'
    ]
    
    # Test 1: Replace traditional SP Score with xERA
    physics_features = [
        'home_sp_xERA', 'away_sp_xERA', 'home_bp_score', 'away_bp_score', 
        'home_fatigue', 'away_fatigue', 'home_lineup_mult', 'away_lineup_mult', 
        'temp', 'park_factor', 'umpire_multiplier'
    ]
    
    # Test 2: Give the AI both
    hybrid_features = base_features + ['home_sp_xERA', 'away_sp_xERA']

    # Handle missing data gracefully
    fill_values = {
        'temp': 72.0, 'park_factor': 100.0, 'umpire_multiplier': 1.0,
        'home_fatigue': 0.0, 'away_fatigue': 0.0,
        'home_lineup_mult': 1.0, 'away_lineup_mult': 1.0,
        'home_sp_xERA': 4.50, 'away_sp_xERA': 4.50, # League average fallback
        'home_sp_score': 4.50, 'away_sp_score': 4.50
    }
    
    df = df.fillna(value=fill_values).dropna(subset=['actual_home_score', 'actual_away_score'])

    X_base = df[base_features]
    X_phys = df[physics_features]
    X_hybrid = df[hybrid_features]
    y = df['run_diff']

    # Create fixed data splits so the tests are identical
    indices = np.arange(len(df))
    idx_train, idx_test = train_test_split(indices, test_size=0.2, random_state=42)

    results = {}

    print("\n🧪 Running ML Experiments... \n")

    # --- Model 1: Baseline ---
    scaler_base = StandardScaler()
    X_train_base = scaler_base.fit_transform(X_base.iloc[idx_train])
    X_test_base = scaler_base.transform(X_base.iloc[idx_test])
    
    rf_base = RandomForestRegressor(n_estimators=500, max_depth=5, min_samples_leaf=10, random_state=42, n_jobs=-1)
    rf_base.fit(X_train_base, y.iloc[idx_train])
    
    preds_base = rf_base.predict(X_test_base)
    acc_base = accuracy_score((y.iloc[idx_test] > 0), (preds_base > 0)) * 100
    results['1. Baseline (Traditional ERA)'] = acc_base

    # --- Model 2: Physics Only (xERA) ---
    scaler_phys = StandardScaler()
    X_train_phys = scaler_phys.fit_transform(X_phys.iloc[idx_train])
    X_test_phys = scaler_phys.transform(X_phys.iloc[idx_test])
    
    rf_phys = RandomForestRegressor(n_estimators=500, max_depth=5, min_samples_leaf=10, random_state=42, n_jobs=-1)
    rf_phys.fit(X_train_phys, y.iloc[idx_train])
    
    preds_phys = rf_phys.predict(X_test_phys)
    acc_phys = accuracy_score((y.iloc[idx_test] > 0), (preds_phys > 0)) * 100
    results['2. Physics Upgrade (xERA Only)'] = acc_phys

    # --- Model 3: Hybrid (Both) ---
    scaler_hybrid = StandardScaler()
    X_train_hyb = scaler_hybrid.fit_transform(X_hybrid.iloc[idx_train])
    X_test_hyb = scaler_hybrid.transform(X_hybrid.iloc[idx_test])
    
    rf_hybrid = RandomForestRegressor(n_estimators=500, max_depth=5, min_samples_leaf=10, random_state=42, n_jobs=-1)
    rf_hybrid.fit(X_train_hyb, y.iloc[idx_train])
    
    preds_hyb = rf_hybrid.predict(X_test_hyb)
    acc_hybrid = accuracy_score((y.iloc[idx_test] > 0), (preds_hyb > 0)) * 100
    results['3. The Hybrid Model (Traditional + xERA)'] = acc_hybrid

    # --- Print Leaderboard ---
    print("🏆 --- MONEYLINE AI LEADERBOARD (Implied Win Rate) --- 🏆")
    print("Higher is better.\n")
    
    sorted_results = sorted(results.items(), key=lambda item: item[1], reverse=True)
    
    baseline_acc = results['1. Baseline (Traditional ERA)']
    for rank, (name, acc) in enumerate(sorted_results, 1):
        if name == '1. Baseline (Traditional ERA)':
            print(f"{rank}. {name:<40} {acc:.1f}%")
        else:
            diff = acc - baseline_acc
            sign = "+" if diff > 0 else ""
            print(f"{rank}. {name:<40} {acc:.1f}% ({sign}{diff:.1f}% vs baseline)")
            
    print("\n=======================================================")

if __name__ == "__main__":
    run_xstats_laboratory()