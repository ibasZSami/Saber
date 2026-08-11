import sqlite3
import os
import logging
from typing import List, Dict, Any

class Database:
    def __init__(self, db_path: str = r"data\memory\memory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS long_term_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def set_memory(self, key: str, value: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO long_term_memory (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, timestamp=CURRENT_TIMESTAMP
            """, (key, value))
            conn.commit()

    def delete_memory(self, key: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM long_term_memory WHERE key = ?", (key,))
            conn.commit()

    def get_all_memories(self) -> Dict[str, str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM long_term_memory")
            rows = cursor.fetchall()
            return {r[0]: r[1] for r in rows}

    def add_history(self, role: str, content: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO conversation_history (role, content) VALUES (?, ?)", (role, content))
            conn.commit()

    def get_recent_history(self, limit: int = 10) -> List[Dict[str, str]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT role, content FROM conversation_history ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            rows.reverse()
            return [{"role": r[0], "content": r[1]} for r in rows]
