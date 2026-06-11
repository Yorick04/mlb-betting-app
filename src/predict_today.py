import sqlite3
import pandas as pd
import joblib
import xgboost as xgb
from datetime import datetime
import pytz
import os, json, gspread
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

load_dotenv(override=True)

def get_google_sheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_info = json.loads(os.getenv("GOOGLE_SHEETS_JSON"))
    return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope))

def run_daily_predictions():
    print("--- 🤖 MLB AI Daily Predictor ---")
    
    # Automatically resolve the root directory path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    
    try:
        model_ml = joblib.load(os.path.join(root_dir, 'mlb_ml_model.pkl'))
        model_home = joblib.load(os.path.join(root_dir, 'mlb_home_model.pkl'))
        model_away = joblib.load(os.path.join(root_dir, 'mlb_away_model.pkl'))
        scaler = joblib.load(os.path.join(root_dir, 'scaler.pkl'))
        print("✅ Successfully loaded ML Model, Split Models, and Scaler.")
    except FileNotFoundError:
        print("❌ Error: Could not find the required .pkl files.")
        return

    db_path = os.path.join(root_dir, "mlb_historical_data.db")
    conn = sqlite3.connect(db_path)
    query = "SELECT * FROM game_logs WHERE status = 'PENDING'"
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("\n⚾ No pending games found in the database.")
        return

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
    
    fallback_defaults = {
        'home_sp_score': 4.50, 'away_sp_score': 4.50, 
        'home_bp_score': 4.50, 'away_bp_score': 4.50, 
        'home_fatigue': 0.0, 'away_fatigue': 0.0, 
        'home_lineup_mult': 1.0, 'away_lineup_mult': 1.0, 
        'temp': 72.0, 'park_factor': 100.0, 'umpire_multiplier': 1.0,
        'wind_impact': 0.0
    }
    
    df[features] = df[features].fillna(fallback_defaults)
    X = df[features]
    X_scaled = scaler.transform(X)

    df['ai_projected_diff'] = model_ml.predict(X_scaled)
    df['ai_projected_home'] = model_home.predict(X_scaled)
    df['ai_projected_away'] = model_away.predict(X_scaled)
    df['ai_projected_total'] = df['ai_projected_home'] + df['ai_projected_away']

    print("📡 Connecting to Google Sheets...")
    try:
        client = get_google_sheet_client()
        sheet = client.open("mlb-betting-app").worksheet("Master")
        all_rows = sheet.get_all_records()
        row_map = {f"{r.get('Date (CT)', '')}_{r.get('Home', '')}_{r.get('Away', '')}": i for i, r in enumerate(all_rows, start=2)}
    except Exception as e:
        print(f"⚠️ Could not connect to Google Sheets: {e}")
        row_map = {}

    cells_to_update = []

    print("="*65)
    print("🏟️ TODAY'S AI PREDICTIONS")
    print("="*65)

    df_sorted = df.reindex(df['ai_projected_diff'].abs().sort_values(ascending=False).index)

    for index, row in df_sorted.iterrows():
        home = row['home_team']
        away = row['away_team']
        matchup = f"{away} @ {home}"
        predicted_diff = row['ai_projected_diff']
        predicted_total = row['ai_projected_total']
        
        exp_home = row['ai_projected_home']
        exp_away = row['ai_projected_away']
        
        if predicted_diff > 0:
            ml_pick_str = "HOME"
            pick_display = f"🏠 HOME ({home})"
            margin = predicted_diff
        else:
            ml_pick_str = "AWAY"
            pick_display = f"✈️ AWAY ({away})"
            margin = abs(predicted_diff)
            
        if margin >= 1.0:
            stars_ml = "★★★" if margin >= 2.0 else "★★" if margin >= 1.5 else "★"
            ml_sheet_val = f"{ml_pick_str} | {stars_ml}"
        else:
            ml_sheet_val = "PASS"

        ou_total = row.get('ou_total', 'N/A')
        ou_sheet_val = "PASS"
        
        if pd.notna(ou_total) and str(ou_total) != 'N/A':
            try:
                line = float(ou_total)
                edge = abs(predicted_total - line)
                if edge >= 0.75:
                    stars_ou = "★★★" if edge >= 2.0 else "★★" if edge >= 1.25 else "★"
                    ou_dir = "OVER" if predicted_total > line else "UNDER"
                    ou_sheet_val = f"{ou_dir} {line} | {stars_ou}"
            except:
                pass
                
        print(f"\n{matchup}")
        print(f"   Proj Score: {home} {exp_home:.1f} | {away} {exp_away:.1f} (Total: {predicted_total:.1f})")
        print(f"   ML Pick: {pick_display} by {margin:.2f} runs -> {ml_sheet_val}")
        print(f"   OU Pick: Projected Total: {predicted_total:.2f} -> {ou_sheet_val}")

        game_key = f"{row['game_date']}_{home}_{away}"
        if game_key in row_map:
            row_idx = row_map[game_key]
            cells_to_update.extend([
                gspread.Cell(row=row_idx, col=10, value=round(exp_home, 2)),
                gspread.Cell(row=row_idx, col=11, value=round(exp_away, 2)),
                gspread.Cell(row=row_idx, col=12, value=round(predicted_total, 2)),
                gspread.Cell(row=row_idx, col=13, value=round(row['home_sp_score'], 2)),
                gspread.Cell(row=row_idx, col=14, value=round(row['away_sp_score'], 2)),
                gspread.Cell(row=row_idx, col=15, value=round(row['home_bp_score'], 2)),
                gspread.Cell(row=row_idx, col=16, value=round(row['away_bp_score'], 2)),
                gspread.Cell(row=row_idx, col=17, value=round(row['home_fatigue'], 2)),
                gspread.Cell(row=row_idx, col=18, value=round(row['away_fatigue'], 2)),
                gspread.Cell(row=row_idx, col=23, value=ou_sheet_val),
                gspread.Cell(row=row_idx, col=24, value=ml_sheet_val)
            ])

    if cells_to_update:
        try:
            sheet.update_cells(cells_to_update)
            print(f"\n✅ Successfully updated spreadsheet columns with live features, metrics, and projections!")
        except Exception as e:
            print(f"\n❌ Error writing to Google Sheets: {e}")

if __name__ == "__main__":
    run_daily_predictions()