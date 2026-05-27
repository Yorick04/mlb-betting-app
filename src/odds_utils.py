import os, requests, pytz
from dotenv import load_dotenv
from datetime import datetime, timedelta
import db_manager

load_dotenv(override=True)

session = requests.Session()

TEAM_MAP = {
    "Oakland Athletics": "Athletics", "Sacramento Athletics": "Athletics", "Oakland A's": "Athletics",
    "St Louis Cardinals": "St. Louis Cardinals", "St. Louis Cardinals": "St. Louis Cardinals",
    "LA Dodgers": "Los Angeles Dodgers", "LA Angels": "Los Angeles Angels",
    "NY Yankees": "New York Yankees", "NY Mets": "New York Mets",
    "Arizona D-backs": "Arizona Diamondbacks", "Arizona Diamondbacks": "Arizona Diamondbacks"
}

def get_mlb_odds():
    api_key = os.getenv("ODDS_API_KEY")
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
    params = {
        'apiKey': api_key, 
        'regions': 'us', 
        'markets': 'h2h,totals,spreads', 
        'bookmakers': 'draftkings', 
        'oddsFormat': 'american'
    }
    
    try:
        data = session.get(url, params=params).json()
        odds_dict = {}
        
        now_utc = datetime.now(pytz.utc)
        today_ct_str = now_utc.astimezone(pytz.timezone('US/Central')).strftime('%Y-%m-%d')
        
        for game in data:
            comm_utc = datetime.strptime(game['commence_time'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
            comm_ct = comm_utc.astimezone(pytz.timezone('US/Central'))
            date_str = comm_ct.strftime('%Y-%m-%d')
            
            # Strict lockout: Discard mismatched dates and games that went live more than 5 minutes ago
            if date_str != today_ct_str:
                continue 
                
            if now_utc > (comm_utc + timedelta(minutes=5)):
                continue 
                
            home = TEAM_MAP.get(game['home_team'], game['home_team'])
            away = TEAM_MAP.get(game['away_team'], game['away_team'])
            key = db_manager.generate_game_id(date_str, home, away)
            
            odds_data = {
                'game_id': key,
                'game_date': date_str,
                'home_team': home,
                'away_team': away,
                'ml_home': "N/A", 'ml_away': "N/A", 'total': "N/A", 'ou_total': "N/A", 'spread': "N/A",
                'rl_home_point': "N/A", 'rl_home_price': "N/A",
                'rl_away_point': "N/A", 'rl_away_price': "N/A",
                'book': 'DraftKings'
            }
            
            for book in game.get('bookmakers', []):
                for market in book.get('markets', []):
                    if market['key'] == 'h2h':
                        odds_data['ml_home'] = next((o['price'] for o in market['outcomes'] if TEAM_MAP.get(o['name'], o['name']) == home), "N/A")
                        odds_data['ml_away'] = next((o['price'] for o in market['outcomes'] if TEAM_MAP.get(o['name'], o['name']) == away), "N/A")
                    elif market['key'] == 'totals':
                        point = market['outcomes'][0].get('point', 'N/A')
                        odds_data['total'] = point
                        odds_data['ou_total'] = point
                    elif market['key'] == 'spreads':
                        # Final transformation: Lock onto the standard +/- 1.5 runline to reject wild alternate spreads
                        standard_outcomes = [o for o in market['outcomes'] if abs(float(o.get('point', 0))) == 1.5]
                        target_outcomes = standard_outcomes if standard_outcomes else market['outcomes']
                        
                        for o in target_outcomes:
                            if TEAM_MAP.get(o['name'], o['name']) == home:
                                odds_data['rl_home_point'] = o.get('point', "N/A")
                                odds_data['rl_home_price'] = o.get('price', "N/A")
                                odds_data['spread'] = o.get('point', "N/A")
                            else:
                                odds_data['rl_away_point'] = o.get('point', "N/A")
                                odds_data['rl_away_price'] = o.get('price', "N/A")

            odds_dict[key] = odds_data
        return odds_dict
    except Exception as e:
        print(f"Error fetching odds: {e}")
        return {}