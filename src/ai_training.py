import sqlite3
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score
import joblib

def train_mybaseball_pal_ai():
    # 1. Connect and Fetch
    print("📥 Fetching historical data from SQLite...")
    conn = sqlite3.connect("mlb_historical_data.db")
    
    query = "SELECT * FROM game_logs WHERE status = 'FINAL'"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if len(df) < 500:
        print(f"❌ Not enough data. You have {len(df)} games; you need at least 500.")
        return
        
    print(f"✅ Loaded {len(df)} games.")

    # 2. Advanced Feature Engineering
    # We calculate the Run Differential as a target, which is often 
    # more predictable than raw scoring totals.
    df['run_diff'] = df['actual_home_score'] - df['actual_away_score']
    
    features = [
        'home_sp_score', 'away_sp_score', 
        'home_bp_score', 'away_bp_score', 
        'home_fatigue', 'away_fatigue', 
        'home_lineup_mult', 'away_lineup_mult', 
        'temp', 'park_factor', 'umpire_multiplier'
    ]
    
    # 3. Intelligent Null Screening (Imputation)
    fill_values = {
        'temp': 72.0,
        'park_factor': 100.0,
        'umpire_multiplier': 1.0,
        'home_fatigue': 0.0,
        'away_fatigue': 0.0,
        'home_lineup_mult': 1.0,
        'away_lineup_mult': 1.0
    }
    
    df = df.fillna(value=fill_values)
    df = df.dropna(subset=['actual_home_score', 'actual_away_score'])
    
    print(f"✅ Data Sanitized: {len(df)} games ready for training.")

    X = df[features]
    y = df['run_diff'] # Changed target to Run Differential

    # 4. Scale Features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # 5. Train/Test Split
    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)

    # 6. Initialize and Train
    # Using a slightly larger forest and depth to capture complex non-linear patterns
    model = RandomForestRegressor(
        n_estimators=500, 
        max_depth=12, 
        min_samples_leaf=15, 
        random_state=42,
        n_jobs=-1
    )
    
    print("🤖 Training model on Run Differential...")
    model.fit(X_train, y_train)

    # 7. Evaluation
    predictions = model.predict(X_test)
    mae = mean_absolute_error(y_test, predictions)
    r2 = r2_score(y_test, predictions)
    
    print("\n--- Model Performance Report (Run Differential) ---")
    print(f"Mean Absolute Error: {mae:.2f} runs")
    print(f"R^2 Score: {r2:.3f}")
    print("--------------------------------\n")
    
    # 8. Feature Importance
    importance = pd.Series(model.feature_importances_, index=features).sort_values(ascending=False)
    print("📊 Top Influencing Factors:")
    print(importance.head(5))

    print("\n✅ Training complete! The model now predicts run differential instead of raw scores.")

    # 9. Save the Model and Scaler for Production
    print("\n💾 Saving model and scaler for daily predictions...")
    joblib.dump(model, 'mlb_model.pkl')
    joblib.dump(scaler, 'scaler.pkl')
    print("✅ Model successfully saved as 'mlb_model.pkl'")
    print("✅ Scaler successfully saved as 'scaler.pkl'")

if __name__ == "__main__":
    train_mybaseball_pal_ai()