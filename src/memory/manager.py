import logging
from typing import List, Dict
from src.memory.database import Database

class MemoryManager:
    def __init__(self, db: Database = None):
        self.db = db or Database()

    def remember(self, key: str, value: str):
        self.db.set_memory(key, value)
        logging.info(f"Memory saved: {key} = {value}")

    def forget(self, key: str):
        self.db.delete_memory(key)
        logging.info(f"Memory deleted: {key}")

    def get_memories(self) -> Dict[str, str]:
        return self.db.get_all_memories()

    def record_turn(self, user_text: str, ai_response: str):
        if user_text:
            self.db.add_history("user", user_text)
        if ai_response:
            self.db.add_history("assistant", ai_response)

    def get_history(self, limit: int = 10) -> List[Dict[str, str]]:
        return self.db.get_recent_history(limit)
