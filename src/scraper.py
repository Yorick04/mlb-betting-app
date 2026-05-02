import os
import json
import gspread
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

load_dotenv()

def get_google_sheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    if "GOOGLE_SHEETS_JSON" in os.environ:
        creds_info = json.loads(os.environ["GOOGLE_SHEETS_JSON"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
    else:
        # This tells Python: "Look in the folder where THIS script is, then go UP one level"
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        key_path = os.path.join(parent_dir, 'service_account_key.json')
        
        creds = ServiceAccountCredentials.from_json_keyfile_name(key_path, scope)
        
    return gspread.authorize(creds)

def get_todays_slate():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"--- Fetching MLB Slate for {today} ---")
    try:
        # Querying the free, official MLB Stats API directly
        # The 'hydrate=probablePitcher' parameter attaches the starting pitchers to the response
        url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher"
        response = requests.get(url)
        data = response.json()
        
        games = []
        if 'dates' in data and len(data['dates']) > 0:
            for game in data['dates'][0]['games']:
                home_team = game['teams']['home']['team']['name']
                away_team = game['teams']['away']['team']['name']
                
                home_pitcher = game['teams']['home'].get('probablePitcher', {}).get('fullName', 'TBA')
                away_pitcher = game['teams']['away'].get('probablePitcher', {}).get('fullName', 'TBA')
                
                games.append({
                    'home_team': home_team,
                    'away_team': away_team,
                    'home_pitcher': home_pitcher,
                    'away_pitcher': away_pitcher
                })
                
        return pd.DataFrame(games)
    except Exception as e:
        print(f"Scraping Error: {e}")
        return None

def run_daily_update():
    sched = get_todays_slate()
    
    if sched is None or sched.empty:
        print("No games found for today.")
        return

    try:
        # The MLB API standardizes our column names, so we don't need the safety checks anymore
        cols_to_keep = ['home_team', 'away_team', 'home_pitcher', 'away_pitcher']
        clean_df = sched[cols_to_keep]

        client = get_google_sheet_client()
        spreadsheet = client.open("mlb-betting-app")
        worksheet = spreadsheet.get_worksheet(0)

        worksheet.clear()
        data_to_upload = [clean_df.columns.values.tolist()] + clean_df.values.tolist()
        worksheet.update(values=data_to_upload, range_name='A1')
        
        print(f"Success! {len(clean_df)} games pushed to 'mlb-betting-app'.")

    except Exception as e:
        print(f"Update Error: {e}")

if __name__ == "__main__":
    run_daily_update()