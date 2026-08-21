import sqlite3
import os
from typing import List, Dict

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
            # FASE 12 (Scheduler) — reminders persisted so "me lembra em 30
            # minutos" survives an app restart within that window.
            # recurring_seconds is NULL for a one-shot reminder; when set, the
            # Scheduler reschedules fire_at instead of deleting the row.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    fire_at REAL NOT NULL,
                    recurring_seconds REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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

    def add_reminder(self, message: str, fire_at: float, recurring_seconds: float = None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO reminders (message, fire_at, recurring_seconds) VALUES (?, ?, ?)",
                (message, fire_at, recurring_seconds),
            )
            conn.commit()
            return cursor.lastrowid

    def get_all_reminders(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, message, fire_at, recurring_seconds FROM reminders")
            rows = cursor.fetchall()
            return [{"id": r[0], "message": r[1], "fire_at": r[2], "recurring_seconds": r[3]} for r in rows]

    def delete_reminder(self, reminder_id: int):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            conn.commit()

    def update_reminder_fire_at(self, reminder_id: int, fire_at: float):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE reminders SET fire_at = ? WHERE id = ?", (fire_at, reminder_id))
            conn.commit()
