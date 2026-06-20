import sqlite3
import os

DB_FILE = "mlb_historical_data.db"

def get_connection():
    """Creates a connection to the SQLite database."""
    return sqlite3.connect(DB_FILE)

def generate_game_id(date_str, home_team, away_team):
    """The universal ID generator used by all scripts."""
    return f"{date_str}_{home_team}_{away_team}"

def setup_database():
    """Creates the necessary tables for Machine Learning if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # We use a single 'flat' table. In Machine Learning, having one wide row 
    # per game with all features and results makes training much easier.
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS game_logs (
        game_id TEXT PRIMARY KEY,
        game_date TEXT,
        home_team TEXT,
        away_team TEXT,
        home_pitcher TEXT,
        away_pitcher TEXT,
        
        -- AI Features (The raw ingredients)
        home_sp_score REAL,
        away_sp_score REAL,
        home_bp_score REAL,
        away_bp_score REAL,
        home_fatigue REAL,
        away_fatigue REAL,
        home_lineup_mult REAL,   
        away_lineup_mult REAL,   
        temp REAL,
        wind_speed REAL,
        wind_dir TEXT,
        park_factor REAL,
        umpire_multiplier REAL,
        
        -- Odds & Projections
        ml_home TEXT,
        ml_away TEXT,
        spread TEXT,
        ou_total TEXT,
        projected_home_runs REAL,
        projected_away_runs REAL,
        
        -- AI Targets (What the AI will try to predict)
        actual_home_score INTEGER,
        actual_away_score INTEGER,
        status TEXT
    )
    ''')
    
    # --- AUTO-PATCH DB SCHEMA ---
    # Safely injects new odds tracking columns into your existing database
    cursor.execute("PRAGMA table_info(game_logs)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "spread_odds" not in columns:
        cursor.execute("ALTER TABLE game_logs ADD COLUMN spread_odds TEXT")
    if "ou_odds" not in columns:
        cursor.execute("ALTER TABLE game_logs ADD COLUMN ou_odds TEXT")
    
    conn.commit()
    conn.close()
    print("✅ SQLite Database verified/created successfully.")

def upsert_game(game_data):
    """Inserts a new game or updates it if it already exists."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Ensure game_id exists based on the standard generator
    if 'game_id' not in game_data and 'game_date' in game_data:
        game_data['game_id'] = generate_game_id(game_data['game_date'], game_data['home_team'], game_data['away_team'])
        
    # Convert 'N/A' strings to actual None (NULL in SQL) for better ML processing later
    clean_data = {k: (None if v == "N/A" else v) for k, v in game_data.items()}
    
    # Ensure our new keys exist in the payload to prevent SQL errors
    if "spread_odds" not in clean_data: clean_data["spread_odds"] = None
    if "ou_odds" not in clean_data: clean_data["ou_odds"] = None
    
    sql = '''
    INSERT INTO game_logs (
        game_id, game_date, home_team, away_team, home_pitcher, away_pitcher,
        home_sp_score, away_sp_score, home_bp_score, away_bp_score, home_fatigue, away_fatigue,
        home_lineup_mult, away_lineup_mult, 
        temp, wind_speed, wind_dir, park_factor, umpire_multiplier,
        ml_home, ml_away, spread, ou_total, spread_odds, ou_odds, projected_home_runs, projected_away_runs, status
    ) VALUES (
        :game_id, :game_date, :home_team, :away_team, :home_pitcher, :away_pitcher,
        :home_sp_score, :away_sp_score, :home_bp_score, :away_bp_score, :home_fatigue, :away_fatigue,
        :home_lineup_mult, :away_lineup_mult, 
        :temp, :wind_speed, :wind_dir, :park_factor, :umpire_multiplier,
        :ml_home, :ml_away, :spread, :ou_total, :spread_odds, :ou_odds, :projected_home_runs, :projected_away_runs, 'PENDING'
    )
    ON CONFLICT(game_id) DO UPDATE SET
        home_sp_score=excluded.home_sp_score,
        away_sp_score=excluded.away_sp_score,
        home_lineup_mult=excluded.home_lineup_mult, 
        away_lineup_mult=excluded.away_lineup_mult, 
        ml_home=COALESCE(excluded.ml_home, game_logs.ml_home),
        ml_away=COALESCE(excluded.ml_away, game_logs.ml_away),
        spread=COALESCE(excluded.spread, game_logs.spread),
        ou_total=COALESCE(excluded.ou_total, game_logs.ou_total),
        spread_odds=COALESCE(excluded.spread_odds, game_logs.spread_odds),
        ou_odds=COALESCE(excluded.ou_odds, game_logs.ou_odds);
    '''
    
    cursor.execute(sql, clean_data)
    conn.commit()
    conn.close()

def update_final_score(game_id, home_score, away_score, status):
    """Updates the actual score in the database after the game finishes."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    UPDATE game_logs 
    SET actual_home_score = ?, actual_away_score = ?, status = ?
    WHERE game_id = ?
    ''', (home_score, away_score, status, game_id))
    
    conn.commit()
    conn.close()

# Run setup when imported
setup_database()