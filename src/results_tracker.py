import os, gspread, requests, json, time, pytz
from datetime import datetime
from scraper import get_google_sheet_client

def update_master_results():
    print("--- Auditing Master Sheet (Catch-Up Mode) ---")
    client = get_google_sheet_client()
    sheet = client.open("mlb-betting-app").worksheet("Master")
    all_rows = sheet.get_all_records()
    
    today_str = datetime.now(pytz.timezone('US/Central')).strftime('%Y-%m-%d')
    
    # 1. Find all dates in the sheet that need grading
    dates_to_check = set()
    for row in all_rows:
        row_date = str(row.get('Date/Time (CT)', ''))
        if row_date and row_date < today_str and not row.get('Actual Total'):
            dates_to_check.add(row_date)

    if not dates_to_check:
        print("No pending games to grade.")
        return

    print(f"Fetching scores for dates: {', '.join(dates_to_check)}")

    # 2. Fetch scores for all missing dates
    scores = {}
    for d in dates_to_check:
        url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={d}"
        try:
            resp = requests.get(url, timeout=15).json()
            for g in resp.get('dates', [{}])[0].get('games', []):
                if g['status']['abstractGameState'] == 'Final':
                    matchup = f"{g['teams']['away']['team']['name']}@{g['teams']['home']['team']['name']}"
                    scores[f"{d}_{matchup}"] = g['teams']['home'].get('score', 0) + g['teams']['away'].get('score', 0)
        except Exception as e:
            print(f"Failed to fetch scores for {d}: {e}")

    # 3. Grade the rows
    for i, row in enumerate(all_rows, start=2):
        row_date = str(row.get('Date/Time (CT)', ''))
        matchup = f"{row.get('Away')}@{row.get('Home')}"
        score_key = f"{row_date}_{matchup}"
        
        # Only grade if it's missing a total AND we have a final score for it
        if not row.get('Actual Total') and score_key in scores:
            actual = scores[score_key]
            line_val = row.get('O/U Total')
            
            res = "PUSH"
            if line_val and str(line_val) != "N/A":
                line = float(line_val)
                alert = str(row.get('Value Alert', '')).upper()
                is_over = any(x in alert for x in ["OVER", "HEAT", "WIND OUT", "NUCLEAR"])
                is_under = any(x in alert for x in ["IN", "PITCHER"])
                
                if is_over:
                    res = "WIN" if actual > line else "LOSS"
                elif is_under:
                    res = "WIN" if actual < line else "LOSS"
                
                if actual == line: res = "PUSH"
            else:
                res = "UNGRADED (No Line)"

            # Update the sheet (with a 1-second delay to prevent Google API timeout)
            sheet.update_cell(i, 14, actual)
            sheet.update_cell(i, 15, res)
            print(f"Graded Row {i}: {matchup} -> {actual} ({res})")
            time.sleep(1)

if __name__ == "__main__":
    update_master_results()