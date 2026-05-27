import os, json, gspread
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials

load_dotenv(override=True)

def get_google_sheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_info = json.loads(os.getenv("GOOGLE_SHEETS_JSON"))
    return gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope))

def calculate_win_rate(w, l):
    if w + l == 0: return 0.0
    return round((w / (w + l)) * 100, 1)

def get_stars(pick_string):
    if "★★★" in pick_string: return "★★★"
    if "★★" in pick_string: return "★★"
    if "★" in pick_string: return "★"
    return None

def run_dashboard():
    print("Fetching graded data from Master Sheet...")
    try:
        client = get_google_sheet_client()
        sheet = client.open("mlb-betting-app").worksheet("Master")
        records = sheet.get_all_records()
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}")
        return

    # Data structures to hold our stats
    stats = {
        "ML": {"W": 0, "L": 0, "P": 0},
        "RL": {"W": 0, "L": 0, "P": 0},
        "TOTAL": {"W": 0, "L": 0, "P": 0},
    }
    
    stars = {
        "★★★": {"W": 0, "L": 0, "P": 0},
        "★★": {"W": 0, "L": 0, "P": 0},
        "★": {"W": 0, "L": 0, "P": 0},
    }

    total_w, total_l, total_p = 0, 0, 0

    for row in records:
        result_str = str(row.get('Result', '')).strip().upper()
        
        # Skip ungraded games or cancelled games
        if not result_str or result_str in ["NO ACTION", "POSTPONED"]:
            continue
            
        t_pick = str(row.get('Total Pick', 'PASS'))
        m_pick = str(row.get('ML Pick', 'PASS'))
        s_pick = str(row.get('Spread Pick', 'PASS'))
        
        # Process Totals
        if t_pick != "PASS" and "T:" in result_str:
            star = get_stars(t_pick)
            if "T: WIN" in result_str:
                stats["TOTAL"]["W"] += 1
                total_w += 1
                if star: stars[star]["W"] += 1
            elif "T: LOSS" in result_str:
                stats["TOTAL"]["L"] += 1
                total_l += 1
                if star: stars[star]["L"] += 1
            elif "T: PUSH" in result_str:
                stats["TOTAL"]["P"] += 1
                total_p += 1
                if star: stars[star]["P"] += 1

        # Process Moneyline
        if m_pick != "PASS" and "ML:" in result_str:
            star = get_stars(m_pick)
            if "ML: WIN" in result_str:
                stats["ML"]["W"] += 1
                total_w += 1
                if star: stars[star]["W"] += 1
            elif "ML: LOSS" in result_str:
                stats["ML"]["L"] += 1
                total_l += 1
                if star: stars[star]["L"] += 1
            elif "ML: PUSH" in result_str:
                stats["ML"]["P"] += 1
                total_p += 1
                if star: stars[star]["P"] += 1

        # Process Runline
        if s_pick != "PASS" and "RL:" in result_str:
            star = get_stars(s_pick)
            if "RL: WIN" in result_str:
                stats["RL"]["W"] += 1
                total_w += 1
                if star: stars[star]["W"] += 1
            elif "RL: LOSS" in result_str:
                stats["RL"]["L"] += 1
                total_l += 1
                if star: stars[star]["L"] += 1
            elif "RL: PUSH" in result_str:
                stats["RL"]["P"] += 1
                total_p += 1
                if star: stars[star]["P"] += 1

    # --- Print Terminal Dashboard ---
    print("\n" + "="*45)
    print(" 📈 MLB QUANT MODEL PERFORMANCE")
    print("="*45)
    
    print(f"\n OVERALL RECORD:  {total_w}W - {total_l}L - {total_p}P")
    print(f" OVERALL WIN %:   {calculate_win_rate(total_w, total_l)}%")
    
    print("\n --- BY MARKET TYPE ---")
    for b_type in ["ML", "RL", "TOTAL"]:
        w, l, p = stats[b_type]["W"], stats[b_type]["L"], stats[b_type]["P"]
        print(f" {b_type.ljust(6)} | {str(w).rjust(2)}W - {str(l).rjust(2)}L - {str(p).rjust(2)}P | {calculate_win_rate(w, l)}%")

    print("\n --- BY CONFIDENCE ---")
    for s_level in ["★★★", "★★", "★"]:
        w, l, p = stars[s_level]["W"], stars[s_level]["L"], stars[s_level]["P"]
        print(f" {s_level.ljust(6)} | {str(w).rjust(2)}W - {str(l).rjust(2)}L - {str(p).rjust(2)}P | {calculate_win_rate(w, l)}%")
        
    print("\n" + "="*45 + "\n")

if __name__ == "__main__":
    run_dashboard()