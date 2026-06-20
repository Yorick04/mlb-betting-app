import os, json, gspread
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

load_dotenv(override=True)

def get_google_sheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_info = json.loads(os.getenv("GOOGLE_SHEETS_JSON"))
    return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope))

def run_performance_report():
    print("📊 Fetching Live Performance Report from Google Sheets...")
    
    try:
        client = get_google_sheet_client()
        sheet = client.open("mlb-betting-app").worksheet("Master")
        all_rows = sheet.get_all_records()
    except Exception as e:
        print(f"❌ Could not connect to Google Sheets: {e}")
        return

    stats = {
        "ML": {"win": 0, "loss": 0, "push": 0},
        "RL": {"win": 0, "loss": 0, "push": 0},
        "T": {"win": 0, "loss": 0, "push": 0}
    }

    for row in all_rows:
        result_str = str(row.get('Result', '')).strip()
        if not result_str or result_str == "NO ACTION" or "POSTPONED" in result_str:
            continue
            
        # Example format: "ML: WIN | RL: LOSS | T: PUSH"
        parts = result_str.split('|')
        for part in parts:
            part = part.strip()
            if not part: continue
            
            try:
                bet_type, outcome = part.split(':')
                bet_type = bet_type.strip()
                outcome = outcome.strip().lower()
                
                if bet_type in stats and outcome in stats[bet_type]:
                    stats[bet_type][outcome] += 1
            except ValueError:
                continue

    print("\n" + "="*45)
    print("📈 AI BETTING PERFORMANCE SUMMARY")
    print("="*45)

    total_wins = 0
    total_losses = 0

    for bet_type, record in stats.items():
        w = record['win']
        l = record['loss']
        p = record['push']
        total_bets = w + l
        
        total_wins += w
        total_losses += l
        
        win_rate = (w / total_bets * 100) if total_bets > 0 else 0.0
        
        name = "Moneyline (ML)" if bet_type == "ML" else "Spread (RL)" if bet_type == "RL" else "Totals (O/U)"
        print(f"⚾ {name}: {w}W - {l}L - {p}P ({win_rate:.1f}% Win Rate)")

    print("-" * 45)
    grand_total = total_wins + total_losses
    grand_win_rate = (total_wins / grand_total * 100) if grand_total > 0 else 0.0
    print(f"🏆 OVERALL RECORD: {total_wins}W - {total_losses}L ({grand_win_rate:.1f}%)")
    print("=" * 45)

if __name__ == "__main__":
    run_performance_report()