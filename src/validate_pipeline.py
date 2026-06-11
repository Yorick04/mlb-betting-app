import os
import sqlite3
import joblib
import numpy as np
import pandas as pd

def run_pipeline_diagnostic():
    print("==================================================")
    print("🔍 MLB PAL ENSEMBLE PIPELINE DIAGNOSTIC")
    print("==================================================\n")
    
    # Dynamically resolve paths relative to this script's location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    
    # 1. Check Artifact Existence
    required_artifacts = {
        "Scaler": "scaler.pkl",
        "Moneyline Model (RF)": "mlb_ml_model.pkl",
        "Home Totals Model (XGB)": "mlb_home_model.pkl",
        "Away Totals Model (XGB)": "mlb_away_model.pkl"
    }
    
    missing_artifacts = False
    print("📁 Checking serialized model artifacts...")
    for name, filename in required_artifacts.items():
        full_path = os.path.join(root_dir, filename)
        if os.path.exists(full_path):
            print(f"   ✅ Found {name}: '{filename}'")
        else:
            print(f"   ❌ Missing {name}: '{filename}'")
            missing_artifacts = True
            
    if missing_artifacts:
        print("\n❌ Diagnostic failed: Core model artifacts are missing. Run ai_training.py first.")
        return

    # 2. Check Database Volume and Schema
    db_path = os.path.join(root_dir, "mlb_historical_data.db")
    print("\n🗄️ Checking SQLite historical database...")
    if not os.path.exists(db_path):
        print(f"   ❌ Error: Database file '{db_path}' not found.")
        return
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check table columns
        cursor.execute("PRAGMA table_info(game_logs)")
        columns = [col[1] for col in cursor.fetchall()]
        
        required_db_cols = ['actual_home_score', 'actual_away_score', 'wind_dir', 'wind_speed', 'game_date']
        for col in required_db_cols:
            if col in columns:
                print(f"   ✅ Database column verified: '{col}'")
            else:
                print(f"   ❌ Missing required database column: '{col}'")
                
        # Check fresh sample size
        cursor.execute("SELECT COUNT(*) FROM game_logs WHERE status = 'FINAL' AND game_date >= '2026-03-01'")
        game_count = cursor.fetchone()[0]
        print(f"   📊 Available 2026 training games in DB: {game_count}")
        if game_count < 500:
            print("   ⚠️ Warning: Sample size is low. Consider running a broader backfill if needed.")
            
        conn.close()
    except Exception as e:
        print(f"   ❌ Database check failed with error: {e}")
        return

    # 3. Model Shape & Inference Validation
    print("\n🧠 Testing model loading and shape tracking...")
    try:
        scaler = joblib.load(os.path.join(root_dir, 'scaler.pkl'))
        model_ml = joblib.load(os.path.join(root_dir, 'mlb_ml_model.pkl'))
        model_home = joblib.load(os.path.join(root_dir, 'mlb_home_model.pkl'))
        model_away = joblib.load(os.path.join(root_dir, 'mlb_away_model.pkl'))
        print("   ✅ All components loaded into memory successfully.")
    except Exception as e:
        print(f"   ❌ Error loading pickle files: {e}")
        return

    # Construct mock single-row game matrix matching the 12 pipeline features
    mock_features = np.array([[4.15, 3.80, 3.90, 4.20, 0.0, 1.0, 1.05, 0.98, 75.0, 102.0, 1.03, 8.5]])
    feature_names = [
        'home_sp_score', 'away_sp_score', 'home_bp_score', 'away_bp_score',
        'home_fatigue', 'away_fatigue', 'home_lineup_mult', 'away_lineup_mult',
        'temp', 'park_factor', 'umpire_multiplier', 'wind_impact'
    ]
    
    mock_df = pd.DataFrame(mock_features, columns=feature_names)
    
    print("\n🎲 Running mock inference through the model matrix...")
    try:
        mock_scaled = scaler.transform(mock_df)
        
        pred_diff = model_ml.predict(mock_scaled)[0]
        pred_home = model_home.predict(mock_scaled)[0]
        pred_away = model_away.predict(mock_scaled)[0]
        pred_total = pred_home + pred_away
        
        print(f"   ✅ Feature Vector Scaled Successfully.")
        print(f"   🔮 Mock Moneyline Prediction (Run Diff): {pred_diff:+.2f}")
        print(f"   🔮 Mock Home Team Expected Runs: {pred_home:.2f}")
        print(f"   🔮 Mock Away Team Expected Runs: {pred_away:.2f}")
        print(f"   🔮 Mock Combined Game Total: {pred_total:.2f}")
        print("\n==================================================")
        print("🎉 SUCCESS: Pipeline matrix is fully aligned!")
        print("==================================================")
    except Exception as e:
        print(f"   ❌ Inference failed.")
        print(f"   💡 Error Detail: {e}")
        print("\n==================================================")
        print("❌ FAILURE: Verify feature ordering in training vs prediction.")
        print("==================================================")

if __name__ == "__main__":
    run_pipeline_diagnostic()