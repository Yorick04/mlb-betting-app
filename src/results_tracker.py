import os, requests, pytz, time, json, gspread
from datetime import datetime
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
import db_manager # <-- IMPORT THE NEW DATABASE MANAGER

load_dotenv(override=True)
session = requests.Session()

def get_google_sheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_info = json.loads(os.getenv("GOOGLE_SHEETS_JSON"))
    return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope))

def update_master_results():
    print("--- Auditing Master Sheet & Database (Live Catch-Up) ---")
    client = get_google_sheet_client()
    sheet = client.open("mlb-betting-app").worksheet("Master")
    all_rows = sheet.get_all_records()
    
    today_str = datetime.now(pytz.timezone('US/Central')).strftime('%Y-%m-%d')
    dates_to_check = set()
    
    for row in all_rows:
        row_date = str(row.get('Date (CT)', ''))
        if row_date and row_date <= today_str and str(row.get('Result', '')).strip() == "":
            dates_to_check.add(row_date)

    if not dates_to_check:
        print("No pending games to grade.")
        return

    scores = {}
    for d in dates_to_check:
        url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={d}"
        try:
            resp = session.get(url, timeout=15).json()
            for date_obj in resp.get('dates', []):
                for g in date_obj.get('games', []):
                    status = g['status']['abstractGameState']
                    detail = g['status']['detailedState']
                    home_team = g['teams']['home']['team']['name']
                    away_team = g['teams']['away']['team']['name']
                    matchup = f"{away_team}@{home_team}"
                    db_game_id = f"{d}_{home_team}_{away_team}" # Used to match our SQLite ID
                    
                    if status == 'Final':
                        scores[f"{d}_{matchup}"] = {
                            "home_score": g['teams']['home'].get('score', 0),
                            "away_score": g['teams']['away'].get('score', 0),
                            "total": g['teams']['home'].get('score', 0) + g['teams']['away'].get('score', 0),
                            "status": "FINAL",
                            "db_id": db_game_id
                        }
                    elif detail in ["Postponed", "Cancelled"]:
                        scores[f"{d}_{matchup}"] = {"status": "PPD", "db_id": db_game_id}
        except: continue

    cells_to_update = []

    for i, row in enumerate(all_rows, start=2):
        row_date = str(row.get('Date (CT)', ''))
        matchup = f"{row.get('Away')}@{row.get('Home')}"
        score_key = f"{row_date}_{matchup}"
        
        if str(row.get('Result', '')).strip() == "" and score_key in scores:
            game_data = scores[score_key]
            
            if game_data["status"] == "PPD":
                # Update Google Sheets
                cells_to_update.append(gspread.Cell(row=i, col=27, value="PPD"))
                cells_to_update.append(gspread.Cell(row=i, col=28, value="POSTPONED"))
                
                # Update SQLite Database
                db_manager.update_final_score(game_data["db_id"], None, None, "PPD")
                continue
                
            actual_home, actual_away, actual_total = game_data["home_score"], game_data["away_score"], game_data["total"]
            formatted_actual = f"H: {actual_home} | A: {actual_away} | T: {actual_total}"
            
            # --- DATABASE UPDATE: Save the final target scores for Machine Learning ---
            db_manager.update_final_score(game_data["db_id"], actual_home, actual_away, "FINAL")
            
            t_pick = str(row.get('Total Pick', 'PASS')).upper()
            m_pick = str(row.get('ML Pick', 'PASS')).upper()
            s_pick = str(row.get('Spread Pick', 'PASS')).upper()
            
            results_str = []
            
            if "OVER" in t_pick or "UNDER" in t_pick:
                try:
                    line = float(row.get('O/U Total'))
                    if actual_total == line: results_str.append("T: PUSH")
                    elif "OVER" in t_pick: results_str.append("T: WIN" if actual_total > line else "T: LOSS")
                    elif "UNDER" in t_pick: results_str.append("T: WIN" if actual_total < line else "T: LOSS")
                except: pass

            if m_pick != "PASS":
                if "HOME" in m_pick: results_str.append("ML: WIN" if actual_home > actual_away else "ML: LOSS")
                elif "AWAY" in m_pick: results_str.append("ML: WIN" if actual_away > actual_home else "ML: LOSS")

            if s_pick != "PASS":
                try:
                    spread_val = float(s_pick.split()[1])
                    if "HOME" in s_pick:
                        adj_home = actual_home + spread_val
                        if adj_home == actual_away: results_str.append("RL: PUSH")
                        else: results_str.append("RL: WIN" if adj_home > actual_away else "RL: LOSS")
                    elif "AWAY" in s_pick:
                        adj_away = actual_away + spread_val
                        if adj_away == actual_home: results_str.append("RL: PUSH")
                        else: results_str.append("RL: WIN" if adj_away > actual_home else "RL: LOSS")
                except: pass

            final_res = " | ".join(results_str) if results_str else "NO ACTION"

            cells_to_update.append(gspread.Cell(row=i, col=27, value=formatted_actual))
            cells_to_update.append(gspread.Cell(row=i, col=28, value=final_res))
            print(f"Graded Row {i}: {matchup} -> {final_res} (Saved to DB)")

    if cells_to_update:
        sheet.update_cells(cells_to_update)
        print(f"Batch updated {len(cells_to_update)} cells successfully.")

if __name__ == "__main__":
    update_master_results()