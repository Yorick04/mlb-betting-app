import os, requests, pytz, time, json, gspread, re
from datetime import datetime
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
import db_manager

load_dotenv(override=True)
session = requests.Session()

def get_google_sheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_info = json.loads(os.getenv("GOOGLE_SHEETS_JSON"))
    return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope))

def extract_line(pick_str):
    try:
        base_pick = pick_str.split('|')[0]
        match = re.search(r'[-+]?\d*\.\d+|\d+', base_pick)
        if match:
            return float(match.group())
    except Exception:
        pass
    return None

def update_master_results():
    print("--- Auditing Master Sheet & Database (Live Catch-Up) ---")
    client = get_google_sheet_client()
    sheet = client.open("mlb-betting-app").worksheet("Master")
    all_rows = sheet.get_all_records()
    
    today_str = datetime.now(pytz.timezone('US/Central')).strftime('%Y-%m-%d')
    dates_to_check = set()
    
    # 1. Check Google Sheet
    for row in all_rows:
        row_date = str(row.get('Date (CT)', ''))
        if row_date and row_date <= today_str and str(row.get('Result', '')).strip() == "":
            dates_to_check.add(row_date)

    # 2. Check Database
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT game_date FROM game_logs WHERE status = 'PENDING' AND game_date <= ?", (today_str,))
    db_pending = cursor.fetchall()
    for (d,) in db_pending:
        dates_to_check.add(d)
    conn.close()

    if not dates_to_check:
        print("No pending games to grade in Sheet or DB.")
        return

    # 3. Fetch Data from MLB API (With Double-Header Support)
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
                    game_num = g.get('gameNumber', 1)
                    
                    db_game_id = f"{d}_{home_team}_{away_team}" 
                    if game_num > 1:
                        db_game_id += f"_G{game_num}"
                        
                    sheet_matchup_key = f"{d}_{home_team}_{away_team}"
                    
                    if sheet_matchup_key not in scores:
                        scores[sheet_matchup_key] = []
                    
                    if status == 'Final':
                        scores[sheet_matchup_key].append({
                            "home_score": g['teams']['home'].get('score', 0),
                            "away_score": g['teams']['away'].get('score', 0),
                            "total": g['teams']['home'].get('score', 0) + g['teams']['away'].get('score', 0),
                            "status": "FINAL",
                            "db_id": db_game_id
                        })
                    elif detail in ["Postponed", "Cancelled"]:
                        scores[sheet_matchup_key].append({"status": "PPD", "db_id": db_game_id})
        except Exception as e: 
            print(f"Error fetching date {d}: {e}")
            continue

    # 4. DATABASE UPDATE
    db_updates = 0
    for key, game_list in scores.items():
        for game_data in game_list:
            if game_data["status"] == "PPD":
                db_manager.update_final_score(game_data["db_id"], None, None, "PPD")
                db_updates += 1
            elif game_data["status"] == "FINAL":
                db_manager.update_final_score(game_data["db_id"], game_data["home_score"], game_data["away_score"], "FINAL")
                db_updates += 1
            
    if db_updates > 0:
        print(f"✅ SQLite Database updated with {db_updates} finalized games.")

    # 5. GOOGLE SHEET UPDATE
    cells_to_update = []
    for i, row in enumerate(all_rows, start=2):
        row_date = str(row.get('Date (CT)', ''))
        score_key = f"{row_date}_{row.get('Home')}_{row.get('Away')}"
        
        if str(row.get('Result', '')).strip() == "" and score_key in scores and len(scores[score_key]) > 0:
            game_data = scores[score_key].pop(0) 
            
            if game_data["status"] == "PPD":
                cells_to_update.append(gspread.Cell(row=i, col=27, value="PPD"))
                cells_to_update.append(gspread.Cell(row=i, col=28, value="POSTPONED"))
                continue
                
            actual_home = game_data["home_score"]
            actual_away = game_data["away_score"]
            actual_total = game_data["total"]
            formatted_actual = f"H: {actual_home} | A: {actual_away} | T: {actual_total}"
            
            # --- FIXED HEADERS: Match exact sheet columns ---
            t_pick = str(row.get('O/U Total Market', 'PASS')).strip().upper()
            m_pick = str(row.get('ML Pick', 'PASS')).strip().upper()
            s_pick = str(row.get('Spread Pick', 'PASS')).strip().upper()
            
            results_str = []
            
            # --- GRADE TOTALS ---
            if t_pick and "PASS" not in t_pick:
                line = extract_line(t_pick)
                if line is None:
                    try:
                        # Fixed to safely catch either variation of your Over/Under base column
                        line = float(row.get('O/U Total Base', row.get('O/U Total', 0)))
                    except:
                        line = 0.0
                        
                if line > 0:
                    if actual_total == line: 
                        results_str.append("T: PUSH")
                    elif "OVER" in t_pick: 
                        results_str.append("T: WIN" if actual_total > line else "T: LOSS")
                    elif "UNDER" in t_pick: 
                        results_str.append("T: WIN" if actual_total < line else "T: LOSS")

            # --- GRADE MONEYLINE ---
            if m_pick and "PASS" not in m_pick:
                if "HOME" in m_pick: 
                    results_str.append("ML: WIN" if actual_home > actual_away else "ML: LOSS")
                elif "AWAY" in m_pick: 
                    results_str.append("ML: WIN" if actual_away > actual_home else "ML: LOSS")

            # --- GRADE SPREAD (RUNLINE) ---
            if s_pick and "PASS" not in s_pick:
                spread_val = extract_line(s_pick)
                if spread_val is not None:
                    if "HOME" in s_pick:
                        adj_home = actual_home + spread_val
                        if adj_home == actual_away: 
                            results_str.append("RL: PUSH")
                        else: 
                            results_str.append("RL: WIN" if adj_home > actual_away else "RL: LOSS")
                    elif "AWAY" in s_pick:
                        adj_away = actual_away + spread_val
                        if adj_away == actual_home: 
                            results_str.append("RL: PUSH")
                        else: 
                            results_str.append("RL: WIN" if adj_away > actual_home else "RL: LOSS")

            final_res = " | ".join(results_str) if results_str else "NO ACTION"

            cells_to_update.append(gspread.Cell(row=i, col=27, value=formatted_actual))
            cells_to_update.append(gspread.Cell(row=i, col=28, value=final_res))
            print(f"Graded Sheet Row {i} -> {final_res}")

    if cells_to_update:
        sheet.update_cells(cells_to_update)
        print(f"Batch updated {len(cells_to_update)} Sheet cells successfully.")
    else:
        print("All completed games are already graded or sheet is clean.")

if __name__ == "__main__":
    update_master_results()