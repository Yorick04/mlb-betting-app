import os, gspread, requests, json, time, pytz
from datetime import datetime
from scraper import get_google_sheet_client

def update_master_results():
    print("--- Auditing Master Sheet (Live Catch-Up) ---")
    client = get_google_sheet_client()
    sheet = client.open("mlb-betting-app").worksheet("Master")
    all_rows = sheet.get_all_records()
    
    # We use US/Central to match your local Huntsville time
    today_str = datetime.now(pytz.timezone('US/Central')).strftime('%Y-%m-%d')
    
    # 1. We now allow current day games (<=) to be checked
    dates_to_check = set()
    for row in all_rows:
        row_date = str(row.get('Date/Time (CT)', ''))
        actual_val = str(row.get('Actual Total', '')).strip()
        
        # FIX: Changed < to <= to include today's finished games
        if row_date and row_date <= today_str and actual_val == "":
            dates_to_check.add(row_date)

    if not dates_to_check:
        print("No pending games to grade.")
        return

    # 2. Bulk fetch scores
    scores = {}
    for d in dates_to_check:
        url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={d}"
        try:
            resp = requests.get(url, timeout=15).json()
            for date_obj in resp.get('dates', []):
                for g in date_obj.get('games', []):
                    status = g['status']['abstractGameState']
                    detail = g['status']['detailedState']
                    matchup = f"{g['teams']['away']['team']['name']}@{g['teams']['home']['team']['name']}"
                    
                    # Capture Final games OR Postponed games
                    if status == 'Final':
                        scores[f"{d}_{matchup}"] = {
                            "total": g['teams']['home'].get('score', 0) + g['teams']['away'].get('score', 0),
                            "status": "FINAL"
                        }
                    elif detail == "Postponed" or detail == "Cancelled":
                        scores[f"{d}_{matchup}"] = {"total": 0, "status": "PPD"}
        except: continue

    # 3. Grade the sheet
    for i, row in enumerate(all_rows, start=2):
        row_date = str(row.get('Date/Time (CT)', ''))
        matchup = f"{row.get('Away')}@{row.get('Home')}"
        score_key = f"{row_date}_{matchup}"
        actual_val = str(row.get('Actual Total', '')).strip()
        
        if actual_val == "" and score_key in scores:
            game_data = scores[score_key]
            actual = game_data["total"]
            status = game_data["status"]
            
            if status == "PPD":
                res = "POSTPONED"
            else:
                pick = str(row.get('Model Pick', ''))
                line_val = row.get('O/U Total')
                res = "PUSH"
                
                if "OVER" in pick or "UNDER" in pick:
                    try:
                        line = float(line_val)
                        if actual == line: res = "PUSH"
                        elif "OVER" in pick: res = "WIN" if actual > line else "LOSS"
                        elif "UNDER" in pick: res = "WIN" if actual < line else "LOSS"
                    except: res = "ERROR"
                else:
                    res = "PASS"

            # Columns 19 and 20 for your 20-column layout
            sheet.update_cell(i, 19, actual)
            sheet.update_cell(i, 20, res)
            print(f"Graded Row {i}: {matchup} -> {actual} ({res})")
            time.sleep(1)

if __name__ == "__main__":
    update_master_results()