# -*- coding: utf-8 -*-
"""
Created on Fri May  8 16:58:35 2026

@author: jorda
"""

import os
import pandas as pd
import requests
import gspread
from datetime import datetime, timedelta
from scraper import get_google_sheet_client

def get_yesterday_results():
    # Get yesterday's date in MLB format
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    url = f"https://statsapi.mlb.com/api/v1/schedule/games/?sportId=1&date={yesterday}"
    
    try:
        response = requests.get(url).json()
        results = {}
        if "dates" in response and response["dates"]:
            for game in response["dates"][0]["games"]:
                home_team = game['teams']['home']['team']['name']
                away_team = game['teams']['away']['team']['name']
                
                # Get scores - handle games that might not be finished/canceled
                if game['status']['abstractGameState'] == 'Final':
                    home_score = game['teams']['home'].get('score', 0)
                    away_score = game['teams']['away'].get('score', 0)
                    total_runs = home_score + away_score
                    
                    results[f"{home_team}_{away_team}"] = total_runs
        return results
    except Exception as e:
        print(f"Error fetching results: {e}")
        return {}

def audit_yesterday_bets():
    print("--- Starting Audit for Yesterday's Games ---")
    
    client = get_google_sheet_client()
    spreadsheet = client.open("mlb-betting-app")
    
    # 1. Pull data from the main tab (Sheet1)
    main_sheet = spreadsheet.sheet1
    all_data = main_sheet.get_all_records()
    
    # 2. Get actual scores from MLB
    actual_scores = get_yesterday_results()
    
    # 3. Connect to Results tab
    try:
        results_sheet = spreadsheet.worksheet("Results")
    except gspread.exceptions.WorksheetNotFound:
        # Create it if you forgot to add it manually
        results_sheet = spreadsheet.add_worksheet(title="Results", rows="100", cols="10")
        results_sheet.append_row(["Date", "Matchup", "Alert", "Line", "Total Runs", "Result"])

    audit_rows = []
    
    for row in all_data:
        home = row['Home']
        away = row['Away']
        matchup_key = f"{home}_{away}"
        alert = row['Value Alert']
        line = row['O/U Total']
        
        if matchup_key in actual_scores and line != "N/A" and alert != "None":
            total_runs = actual_scores[matchup_key]
            line_float = float(line)
            
            # Determine Win/Loss
            result = "PUSH"
            if "OVER" in alert:
                result = "WIN" if total_runs > line_float else "LOSS"
            elif "UNDER" in alert: # For future under logic
                result = "WIN" if total_runs < line_float else "LOSS"
            elif "WIND" in alert:
                # Wind alerts are general; we'll just log if they went over or under
                result = "OVER" if total_runs > line_float else "UNDER"

            if total_runs == line_float:
                result = "PUSH"

            audit_rows.append([
                (datetime.now() - timedelta(days=1)).strftime('%m/%d'),
                f"{away} @ {home}",
                alert,
                line,
                total_runs,
                result
            ])

    if audit_rows:
        results_sheet.append_rows(audit_rows)
        print(f"Audit Complete: {len(audit_rows)} alerts processed.")
    else:
        print("No alerts found to audit for yesterday.")

if __name__ == "__main__":
    audit_yesterday_bets()