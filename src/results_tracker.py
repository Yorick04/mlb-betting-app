import os
import gspread
import requests
import json
from datetime import datetime, timedelta
from scraper import get_google_sheet_client

def update_master_results():
    print("--- Auditing Master Sheet ---")
    client = get_google_sheet_client()
    sheet = client.open("mlb-betting-app").worksheet("Master")
    all_rows = sheet.get_all_records()
    
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={yesterday}"
    
    response = requests.get(url).json()
    scores = {}
    if "dates" in response and response["dates"]:
        for game in response["dates"][0]["games"]:
            if game['status']['abstractGameState'] == 'Final':
                key = f"{game['teams']['away']['team']['name']}@{game['teams']['home']['team']['name']}"
                total = game['teams']['home'].get('score', 0) + game['teams']['away'].get('score', 0)
                scores[key] = total

    for i, row in enumerate(all_rows, start=2):
        matchup = f"{row['Away']}@{row['Home']}"
        if not row.get('Actual Total') and matchup in scores:
            actual_total = scores[matchup]
            line_val = row.get('O/U Total')
            alert = row.get('Value Alert', '')

            if line_val and line_val != "N/A":
                line = float(line_val)
                res = "PUSH"
                if actual_total > line: res = "WIN" if "OVER" in alert else "LOSS"
                elif actual_total < line: res = "LOSS" if "OVER" in alert else "WIN"
                
                sheet.update_cell(i, 12, actual_total) # Column L
                sheet.update_cell(i, 13, res) # Column M
                print(f"Updated {matchup}: {actual_total} ({res})")

if __name__ == "__main__":
    update_master_results()