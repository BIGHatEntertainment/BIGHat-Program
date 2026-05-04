import sqlite3
import os
import json
from pathlib import Path

DB_PATH = Path("data/bighat.db")

def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Venues & Employees (Already done, but ensuring all columns)
    cursor.execute('''CREATE TABLE IF NOT EXISTS venues (
        id TEXT PRIMARY KEY, name TEXT, address TEXT, city TEXT, state TEXT, 
        venue_pays_host_directly INTEGER, created_at TEXT)''')
        
    cursor.execute('''CREATE TABLE IF NOT EXISTS employees (
        id TEXT PRIMARY KEY, name TEXT, email TEXT, phone TEXT, 
        is_admin INTEGER, password_hash TEXT, created_at TEXT)''')
    
    # 2. Events & Roles
    cursor.execute('''CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY, title TEXT, event_type TEXT, venue_id TEXT, date TEXT, 
        duration_hours REAL, claimed_by TEXT, status TEXT, wore_big_hat INTEGER, 
        social_media_posts INTEGER, winners_post INTEGER, is_special_event INTEGER, created_at TEXT)''')
        
    cursor.execute('''CREATE TABLE IF NOT EXISTS venue_roles (
        id TEXT PRIMARY KEY, venue_id TEXT, employee_id TEXT, 
        role_category TEXT, role_type TEXT, created_at TEXT)''')

    # 3. Trivia Presentations (The "Brains" of the shows)
    cursor.execute('''CREATE TABLE IF NOT EXISTS presentations (
        id TEXT PRIMARY KEY, name TEXT, created_by TEXT, created_at TEXT, 
        type TEXT, total_slides INTEGER, data TEXT)''') # data stores JSON metadata

    # 4. Round Usage (The 6-month lockout logic)
    cursor.execute('''CREATE TABLE IF NOT EXISTS round_usage (
        id TEXT PRIMARY KEY, location TEXT, round_file TEXT, round_name TEXT, 
        used_date TEXT, expires_date TEXT, used_by TEXT, presentation_id TEXT)''')

    # 5. Bingo Games
    cursor.execute('''CREATE TABLE IF NOT EXISTS bingo_games (
        id TEXT PRIMARY KEY, type TEXT, settings TEXT, state TEXT, created_at TEXT)''')

    conn.commit()
    conn.close()

def get_db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
