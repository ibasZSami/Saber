from src.memory.database import Database
from src.memory.manager import MemoryManager


def _capture(event_bus, event_type):
    received = []
    event_bus.subscribe(event_type, lambda **kwargs: received.append(kwargs))
    return received


class TestDatabase:
    def test_set_and_get_memory(self, tmp_path):
        db = Database(db_path=str(tmp_path / "mem.db"))
        db.set_memory("cor_favorita", "roxo")
        assert db.get_all_memories() == {"cor_favorita": "roxo"}

    def test_set_memory_overwrites_existing_key(self, tmp_path):
        db = Database(db_path=str(tmp_path / "mem.db"))
        db.set_memory("cor_favorita", "roxo")
        db.set_memory("cor_favorita", "azul")
        assert db.get_all_memories() == {"cor_favorita": "azul"}

    def test_delete_memory(self, tmp_path):
        db = Database(db_path=str(tmp_path / "mem.db"))
        db.set_memory("cor_favorita", "roxo")
        db.delete_memory("cor_favorita")
        assert db.get_all_memories() == {}

    def test_delete_missing_key_is_noop(self, tmp_path):
        db = Database(db_path=str(tmp_path / "mem.db"))
        db.delete_memory("nao_existe")

    def test_history_recent_order(self, tmp_path):
        db = Database(db_path=str(tmp_path / "mem.db"))
        db.add_history("user", "oi")
        db.add_history("assistant", "olá!")
        db.add_history("user", "tudo bem?")

        history = db.get_recent_history(limit=2)

        assert [h["content"] for h in history] == ["olá!", "tudo bem?"]

    def test_history_respects_limit(self, tmp_path):
        db = Database(db_path=str(tmp_path / "mem.db"))
        for i in range(5):
            db.add_history("user", f"msg {i}")

        history = db.get_recent_history(limit=3)

        assert len(history) == 3
        assert history[-1]["content"] == "msg 4"


class TestMemoryManager:
    def test_remember_persists_via_database(self, tmp_path):
        mgr = MemoryManager(db=Database(db_path=str(tmp_path / "mem.db")))
        mgr.remember("cidade", "Sao Paulo")
        assert mgr.get_memories() == {"cidade": "Sao Paulo"}

    def test_forget_removes_key(self, tmp_path):
        mgr = MemoryManager(db=Database(db_path=str(tmp_path / "mem.db")))
        mgr.remember("cidade", "Sao Paulo")
        mgr.forget("cidade")
        assert mgr.get_memories() == {}

    def test_record_turn_skips_empty_strings(self, tmp_path):
        mgr = MemoryManager(db=Database(db_path=str(tmp_path / "mem.db")))
        mgr.record_turn("oi", "")
        history = mgr.get_history()
        assert len(history) == 1
        assert history[0]["role"] == "user"

    def test_record_turn_saves_both_sides(self, tmp_path):
        mgr = MemoryManager(db=Database(db_path=str(tmp_path / "mem.db")))
        mgr.record_turn("oi", "olá!")
        history = mgr.get_history()
        assert [h["role"] for h in history] == ["user", "assistant"]


class TestMemoryManagerEvents:
    def test_remember_emits_memory_created(self, tmp_path):
        mgr = MemoryManager(db=Database(db_path=str(tmp_path / "mem.db")))
        created = _capture(mgr.event_bus, "MEMORY_CREATED")

        mgr.remember("cidade", "Sao Paulo")

        assert created == [{"key": "cidade", "value": "Sao Paulo"}]

    def test_get_memories_emits_memory_recalled_when_nonempty(self, tmp_path):
        mgr = MemoryManager(db=Database(db_path=str(tmp_path / "mem.db")))
        mgr.remember("cidade", "Sao Paulo")
        recalled = _capture(mgr.event_bus, "MEMORY_RECALLED")

        mgr.get_memories()

        assert recalled == [{"count": 1}]

    def test_get_memories_does_not_emit_when_empty(self, tmp_path):
        mgr = MemoryManager(db=Database(db_path=str(tmp_path / "mem.db")))
        recalled = _capture(mgr.event_bus, "MEMORY_RECALLED")

        mgr.get_memories()

        assert recalled == []
