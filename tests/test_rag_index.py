from src.memory.rag_index import RAGIndex


def _write(tmp_path, relpath, content):
    path = tmp_path / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestIndexDirectory:
    def test_indexes_recognized_text_files(self, tmp_path):
        _write(tmp_path, "notes.md", "# Título\nAlgum conteúdo sobre gatos.")
        _write(tmp_path, "app.py", "def login():\n    return True\n")

        index = RAGIndex()
        count = index.index_directory(str(tmp_path))

        assert count > 0
        assert index.chunk_count == count
        assert len(index.indexed_files) == 2

    def test_ignores_files_with_unrecognized_extensions(self, tmp_path):
        _write(tmp_path, "image.png", "not really a png but wrong extension")
        _write(tmp_path, "readme.md", "conteúdo válido")

        index = RAGIndex()
        index.index_directory(str(tmp_path))

        assert len(index.indexed_files) == 1
        assert index.indexed_files[0].endswith("readme.md")

    def test_skips_known_noise_directories(self, tmp_path):
        _write(tmp_path, "node_modules/pkg/index.js", "module.exports = {}")
        _write(tmp_path, ".git/config", "[core]")
        _write(tmp_path, "src/main.py", "print('hello')")

        index = RAGIndex()
        index.index_directory(str(tmp_path))

        assert len(index.indexed_files) == 1
        assert "src" in index.indexed_files[0]

    def test_skips_files_over_the_size_cap(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.memory.rag_index.MAX_FILE_BYTES", 10)
        _write(tmp_path, "big.txt", "this text is definitely longer than ten bytes")

        index = RAGIndex()
        index.index_directory(str(tmp_path))

        assert index.indexed_files == []
        assert len(index.skipped_files) == 1

    def test_skips_undecodable_binary_content(self, tmp_path):
        path = tmp_path / "binary.py"
        path.write_bytes(b"\xff\xfe\x00\x01binary junk")

        index = RAGIndex()
        index.index_directory(str(tmp_path))

        assert index.indexed_files == []
        assert len(index.skipped_files) == 1

    def test_empty_directory_returns_zero(self, tmp_path):
        index = RAGIndex()
        count = index.index_directory(str(tmp_path))
        assert count == 0
        assert index.chunk_count == 0

    def test_reindexing_replaces_the_previous_index(self, tmp_path):
        _write(tmp_path, "a.md", "conteúdo A")
        index = RAGIndex()
        index.index_directory(str(tmp_path))
        first_count = index.chunk_count

        other_dir = tmp_path / "other"
        _write(other_dir, "b.md", "conteúdo B completamente diferente")
        index.index_directory(str(other_dir))

        assert index.indexed_files == [str(other_dir / "b.md")]
        assert first_count > 0

    def test_large_file_is_split_into_multiple_chunks(self, tmp_path):
        lines = [f"linha número {i} com algum texto de preenchimento" for i in range(200)]
        _write(tmp_path, "big.txt", "\n".join(lines))

        index = RAGIndex()
        index.index_directory(str(tmp_path))

        assert index.chunk_count > 1


class TestSearch:
    def test_finds_the_chunk_containing_the_query_term(self, tmp_path):
        _write(tmp_path, "auth.py", "def login(user, password):\n    return check_credentials(user, password)\n")
        _write(tmp_path, "other.py", "def unrelated_stuff():\n    return 42\n")

        index = RAGIndex()
        index.index_directory(str(tmp_path))
        results = index.search("login")

        assert len(results) >= 1
        top_chunk, score = results[0]
        assert "login" in top_chunk.text
        # Not asserting score > 0: BM25's idf term can legitimately land at
        # exactly zero for a term that appears in about half a tiny corpus
        # (see RAGIndex.search's docstring) — the chunk still being returned
        # and ranked first is what matters, not the raw score's sign.
        assert score >= 0

    def test_returns_empty_list_before_anything_is_indexed(self):
        index = RAGIndex()
        assert index.search("anything") == []

    def test_returns_empty_list_for_blank_query(self, tmp_path):
        _write(tmp_path, "a.md", "conteúdo qualquer")
        index = RAGIndex()
        index.index_directory(str(tmp_path))
        assert index.search("   ") == []

    def test_returns_empty_list_when_nothing_matches(self, tmp_path):
        _write(tmp_path, "a.md", "conteúdo sobre gatos e bruxos")
        index = RAGIndex()
        index.index_directory(str(tmp_path))
        assert index.search("xenobiologia quântica intergaláctica") == []

    def test_respects_top_k(self, tmp_path):
        for i in range(10):
            _write(tmp_path, f"doc{i}.md", f"informação repetida {i} sobre gatos mágicos")
        index = RAGIndex()
        index.index_directory(str(tmp_path))
        results = index.search("gatos mágicos", top_k=3)
        assert len(results) <= 3

    def test_includes_line_range_metadata(self, tmp_path):
        _write(tmp_path, "a.py", "def target_function():\n    pass\n")
        index = RAGIndex()
        index.index_directory(str(tmp_path))
        results = index.search("target_function")
        chunk, _score = results[0]
        assert chunk.start_line == 1
        assert chunk.end_line >= 1
        assert chunk.doc_path.endswith("a.py")


class TestClear:
    def test_clear_resets_everything(self, tmp_path):
        _write(tmp_path, "a.md", "conteúdo")
        index = RAGIndex()
        index.index_directory(str(tmp_path))

        index.clear()

        assert index.chunk_count == 0
        assert index.indexed_files == []
        assert index.skipped_files == []
        assert index.search("conteúdo") == []
