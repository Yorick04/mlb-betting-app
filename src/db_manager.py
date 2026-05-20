import sqlite3
import os

DB_FILE = "mlb_historical_data.db"

def get_connection():
    """Creates a connection to the SQLite database."""
    return sqlite3.connect(DB_FILE)

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
        home_lineup_mult REAL,   -- NEW: Added Home Hitter Threat
        away_lineup_mult REAL,   -- NEW: Added Away Hitter Threat
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
    
    conn.commit()
    conn.close()
    print("✅ SQLite Database verified/created successfully.")

def upsert_game(game_data):
    """Inserts a new game or updates it if it already exists."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Convert 'N/A' strings to actual None (NULL in SQL) for better ML processing later
    clean_data = {k: (None if v == "N/A" else v) for k, v in game_data.items()}
    
    sql = '''
    INSERT INTO game_logs (
        game_id, game_date, home_team, away_team, home_pitcher, away_pitcher,
        home_sp_score, away_sp_score, home_bp_score, away_bp_score, home_fatigue, away_fatigue,
        home_lineup_mult, away_lineup_mult, -- NEW
        temp, wind_speed, wind_dir, park_factor, umpire_multiplier,
        ml_home, ml_away, spread, ou_total, projected_home_runs, projected_away_runs, status
    ) VALUES (
        :game_id, :game_date, :home_team, :away_team, :home_pitcher, :away_pitcher,
        :home_sp_score, :away_sp_score, :home_bp_score, :away_bp_score, :home_fatigue, :away_fatigue,
        :home_lineup_mult, :away_lineup_mult, -- NEW
        :temp, :wind_speed, :wind_dir, :park_factor, :umpire_multiplier,
        :ml_home, :ml_away, :spread, :ou_total, :projected_home_runs, :projected_away_runs, 'PENDING'
    )
    ON CONFLICT(game_id) DO UPDATE SET
        home_sp_score=excluded.home_sp_score,
        away_sp_score=excluded.away_sp_score,
        home_lineup_mult=excluded.home_lineup_mult, -- NEW
        away_lineup_mult=excluded.away_lineup_mult, -- NEW
        ml_home=excluded.ml_home,
        ml_away=excluded.ml_away,
        spread=excluded.spread,
        ou_total=excluded.ou_total;
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