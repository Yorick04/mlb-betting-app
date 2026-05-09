import os, gspread, requests, json
from datetime import datetime, timedelta
from scraper import get_google_sheet_client

def update_master_results():
    print("--- Auditing Master Sheet (Date-Keyed) ---")
    client = get_google_sheet_client()
    sheet = client.open("mlb-betting-app").worksheet("Master")
    all_rows = sheet.get_all_records()
    
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={yesterday}"
    
    try:
        resp = requests.get(url, timeout=15).json()
        scores = {f"{g['teams']['away']['team']['name']}@{g['teams']['home']['team']['name']}": g['teams']['home'].get('score', 0) + g['teams']['away'].get('score', 0) for g in resp.get('dates', [{}])[0].get('games', []) if g['status']['abstractGameState'] == 'Final'}
    except: return

    for i, row in enumerate(all_rows, start=2):
        matchup = f"{row['Away']}@{row['Home']}"
        row_date = str(row.get('Date/Time (CT)'))
        
        # Only grade if it's from yesterday and doesn't have a score yet
        if row_date == yesterday and not row.get('Actual Total') and matchup in scores:
            actual = scores[matchup]
            line_val = row.get('O/U Total')
            if line_val and line_val != "N/A":
                line = float(line_val)
                alert = str(row.get('Value Alert', '')).upper()
                is_over = any(x in alert for x in ["OVER", "HEAT", "WIND OUT", "NUCLEAR"])
                is_under = any(x in alert for x in ["IN", "PITCHER"])
                
                res = "PUSH"
                if is_over:
                    res = "WIN" if actual > line else "LOSS"
                elif is_under:
                    res = "WIN" if actual < line else "LOSS"
                
                if actual == line: res = "PUSH"
                sheet.update_cell(i, 14, actual)
                sheet.update_cell(i, 15, res)

if __name__ == "__main__":
    update_master_results()