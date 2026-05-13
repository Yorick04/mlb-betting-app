import os, gspread, requests, json, time, pytz
from datetime import datetime
from scraper import get_google_sheet_client

def update_master_results():
    print("--- Auditing Master Sheet (20-Column Mode) ---")
    client = get_google_sheet_client()
    sheet = client.open("mlb-betting-app").worksheet("Master")
    all_rows = sheet.get_all_records()
    
    today_str = datetime.now(pytz.timezone('US/Central')).strftime('%Y-%m-%d')
    
    dates_to_check = set()
    for row in all_rows:
        row_date = str(row.get('Date/Time (CT)', ''))
        actual_val = str(row.get('Actual Total', '')).strip()
        if row_date and row_date < today_str and actual_val == "":
            dates_to_check.add(row_date)

    if not dates_to_check:
        print("No pending games to grade.")
        return

    scores = {}
    for d in dates_to_check:
        url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={d}"
        try:
            resp = requests.get(url, timeout=15).json()
            for g in resp.get('dates', [{}])[0].get('games', []) :
                if g['status']['abstractGameState'] == 'Final':
                    matchup = f"{g['teams']['away']['team']['name']}@{g['teams']['home']['team']['name']}"
                    scores[f"{d}_{matchup}"] = g['teams']['home'].get('score', 0) + g['teams']['away'].get('score', 0)
        except: continue

    for i, row in enumerate(all_rows, start=2):
        row_date = str(row.get('Date/Time (CT)', ''))
        matchup = f"{row.get('Away')}@{row.get('Home')}"
        score_key = f"{row_date}_{matchup}"
        actual_val = str(row.get('Actual Total', '')).strip()
        
        if actual_val == "" and score_key in scores:
            actual = scores[score_key]
            pick = str(row.get('Model Pick', ''))
            line_val = row.get('O/U Total')
            
            res = "PUSH"
            if "OVER" in pick or "UNDER" in pick:
                try:
                    line = float(line_val)
                    if actual == line: res = "PUSH"
                    elif "OVER" in pick: res = "WIN" if actual > line else "LOSS"
                    elif "UNDER" in pick: res = "WIN" if actual < line else "LOSS"
                except: res = "ERROR (Check Line)"
            else: res = "PASS"

            # Update Columns 19 (Actual Total) and 20 (Result)
            sheet.update_cell(i, 19, actual)
            sheet.update_cell(i, 20, res)
            print(f"Graded Row {i}: {matchup} -> {actual} ({res})")
            time.sleep(1)

if __name__ == "__main__":
    update_master_results()