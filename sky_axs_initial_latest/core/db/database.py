import sqlite3
import json
import os
from typing import List, Dict, Any

DB_PATH = os.getenv("ENDPOINT_DB", "/app/data/endpoints.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS endpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target TEXT,
                method TEXT,
                url TEXT,
                params TEXT,
                headers TEXT,
                cookies TEXT,
                response_body TEXT,
                status_code INTEGER,
                content_type TEXT,
                sensitive BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
