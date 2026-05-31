import sqlite3
import pandas as pd
import joblib
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
    
    # 1. Load BOTH trained AI models and the scaler
    try:
        model_ml = joblib.load('mlb_ml_model.pkl')
        model_ou = joblib.load('mlb_ou_model.pkl')
        scaler = joblib.load('scaler.pkl')
        print("✅ Successfully loaded ML Model, OU Model, and Scaler.")
    except FileNotFoundError:
        print("❌ Error: Could not find the required .pkl files.")
        print("Make sure you have run your ai_training.py script first!")
        return

    # 2. Fetch today's pending games from the database
    conn = sqlite3.connect("mlb_historical_data.db")
    query = "SELECT * FROM game_logs WHERE status = 'PENDING'"
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("\n⚾ No pending games found in the database.")
        print("Make sure you run your daily scraper first so the AI has games to predict!")
        return

    print(f"🔍 Analyzing {len(df)} upcoming games...\n")

    # 3. Prepare the features
    features = [
        'home_sp_score', 'away_sp_score', 
        'home_bp_score', 'away_bp_score', 
        'home_fatigue', 'away_fatigue', 
        'home_lineup_mult', 'away_lineup_mult', 
        'temp', 'park_factor', 'umpire_multiplier'
    ]
    
    # Handle missing values to prevent scaler crashes
    df[features] = df[features].fillna(df[features].mean())
    X = df[features]
    X_scaled = scaler.transform(X)

    # 4. Generate Predictions
    df['ai_projected_diff'] = model_ml.predict(X_scaled)
    df['ai_projected_total'] = model_ou.predict(X_scaled)

    # 5. Connect to Google Sheets to map rows
    print("📡 Connecting to Google Sheets to write AI picks...")
    try:
        client = get_google_sheet_client()
        sheet = client.open("mlb-betting-app").worksheet("Master")
        all_rows = sheet.get_all_records()
        
        row_map = {}
        for i, r in enumerate(all_rows, start=2): # start=2 because row 1 is headers
            key = f"{r.get('Date (CT)', '')}_{r.get('Home', '')}_{r.get('Away', '')}"
            row_map[key] = i
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
        
        # --- CALCULATE EXACT TEAM TOTALS ---
        exp_home = (predicted_total + predicted_diff) / 2
        exp_away = (predicted_total - predicted_diff) / 2
        
        # --- MONEYLINE LOGIC ---
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

        # --- OVER/UNDER LOGIC ---
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

        # Queue the Google Sheet updates
        game_key = f"{row['game_date']}_{home}_{away}"
        if game_key in row_map:
            row_idx = row_map[game_key]
            
            # Write Projections to columns 10, 11, 12
            cells_to_update.append(gspread.Cell(row=row_idx, col=10, value=round(exp_home, 2)))
            cells_to_update.append(gspread.Cell(row=row_idx, col=11, value=round(exp_away, 2)))
            cells_to_update.append(gspread.Cell(row=row_idx, col=12, value=round(predicted_total, 2)))
            
            # FORCE SYNC SCORING FEATURES (Cols 13-18)
            cells_to_update.append(gspread.Cell(row=row_idx, col=13, value=round(row['home_sp_score'], 2)))
            cells_to_update.append(gspread.Cell(row=row_idx, col=14, value=round(row['away_sp_score'], 2)))
            cells_to_update.append(gspread.Cell(row=row_idx, col=15, value=round(row['home_bp_score'], 2)))
            cells_to_update.append(gspread.Cell(row=row_idx, col=16, value=round(row['away_bp_score'], 2)))
            cells_to_update.append(gspread.Cell(row=row_idx, col=17, value=round(row['home_fatigue'], 2)))
            cells_to_update.append(gspread.Cell(row=row_idx, col=18, value=round(row['away_fatigue'], 2)))
            
            # Write Picks to columns 23, 24
            cells_to_update.append(gspread.Cell(row=row_idx, col=23, value=ou_sheet_val))
            cells_to_update.append(gspread.Cell(row=row_idx, col=24, value=ml_sheet_val))

    # Execute Batch Update
    if cells_to_update:
        try:
            sheet.update_cells(cells_to_update)
            print(f"\n✅ Successfully updated spreadsheet columns with live features, metrics, and projections!")
        except Exception as e:
            print(f"\n❌ Error writing to Google Sheets: {e}")

if __name__ == "__main__":
    run_daily_predictions()