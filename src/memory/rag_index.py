import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from rank_bm25 import BM25Okapi

# Only files recognizable as plain text/code get indexed — anything else
# (images, binaries, compiled artifacts) either can't be decoded as UTF-8 or
# would just add noise to a keyword search.
INDEXABLE_EXTENSIONS = {
    ".txt", ".md", ".rst",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".php", ".sh", ".ps1",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".html", ".css", ".sql",
}

# Directories never worth walking into — dependency trees, VCS internals, and
# build output are large, mostly noise for a keyword search, and in the case
# of .git can be genuinely huge.
SKIPPED_DIR_NAMES = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    ".pytest_cache", ".mypy_cache", "target", ".idea", ".vscode",
}

MAX_FILE_BYTES = 2 * 1024 * 1024  # skip anything past 2MB — logs, dumps, etc.
MAX_FILES_PER_INDEX = 2000  # hard cap so one index_folder call can't hang on a huge tree

CHUNK_LINES = 40
CHUNK_OVERLAP_LINES = 5

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_À-ÿ]+")


@dataclass(frozen=True)
class RAGChunk:
    doc_path: str
    start_line: int
    end_line: int
    text: str


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _chunk_lines(lines: List[str]) -> List[Tuple[int, int, str]]:
    """(start_line, end_line, text) triples, 1-indexed, with a small overlap
    so a match that straddles a chunk boundary isn't lost entirely from
    either side."""
    chunks = []
    step = max(1, CHUNK_LINES - CHUNK_OVERLAP_LINES)
    i = 0
    while i < len(lines):
        chunk = lines[i:i + CHUNK_LINES]
        if chunk:
            chunks.append((i + 1, i + len(chunk), "\n".join(chunk)))
        if i + CHUNK_LINES >= len(lines):
            break
        i += step
    return chunks


class RAGIndex:
    """Local, offline document/code search — deliberately BM25 (sparse
    keyword ranking) instead of embeddings: no model download, no GPU/heavy
    ML dependency, no per-file API cost, and everything stays on disk. Good
    enough for "find the file/function that mentions X" over a personal
    folder or small-to-medium repo; not a semantic search engine.

    In-memory only, rebuilt from scratch on each index_folder call — no
    persistence, no incremental re-indexing, no file-watching. Simplest
    thing that works for a first version; if content changes, the user
    re-indexes."""

    def __init__(self):
        self._chunks: List[RAGChunk] = []
        self._tokenized_chunks: List[List[str]] = []
        self._bm25: Optional[BM25Okapi] = None
        self.indexed_files: List[str] = []
        self.skipped_files: List[Tuple[str, str]] = []

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def clear(self) -> None:
        self._chunks = []
        self._tokenized_chunks = []
        self._bm25 = None
        self.indexed_files = []
        self.skipped_files = []

    def index_directory(self, dir_path: str) -> int:
        """Replaces any previous index with a fresh one built from dir_path.
        Returns the number of chunks indexed (0 means nothing indexable was
        found — an empty/wrong path, or a folder with no recognized text/code
        files)."""
        self.clear()
        scanned = 0
        for root, dirnames, filenames in os.walk(dir_path):
            dirnames[:] = [d for d in dirnames if d not in SKIPPED_DIR_NAMES]
            for filename in filenames:
                if scanned >= MAX_FILES_PER_INDEX:
                    break
                path = os.path.join(root, filename)
                ext = os.path.splitext(filename)[1].lower()
                if ext not in INDEXABLE_EXTENSIONS:
                    continue
                scanned += 1
                self._index_file(path)
            if scanned >= MAX_FILES_PER_INDEX:
                break

        if self._chunks:
            self._tokenized_chunks = [_tokenize(c.text) for c in self._chunks]
            self._bm25 = BM25Okapi(self._tokenized_chunks)
        return len(self._chunks)

    def _index_file(self, path: str) -> None:
        try:
            if os.path.getsize(path) > MAX_FILE_BYTES:
                self.skipped_files.append((path, "arquivo grande demais"))
                return
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            self.skipped_files.append((path, str(e)))
            return

        lines = text.splitlines()
        for start_line, end_line, chunk_text in _chunk_lines(lines):
            if chunk_text.strip():
                self._chunks.append(RAGChunk(path, start_line, end_line, chunk_text))
        self.indexed_files.append(path)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[RAGChunk, float]]:
        """Ranks by BM25 score, but the actual relevance gate is literal
        token overlap with the query, not score > 0 — BM25's classic idf
        term (log((N-freq+0.5)/(freq+0.5))) legitimately lands at exactly
        zero, not just negative, whenever a term appears in about half the
        indexed chunks, which happens constantly on the small corpora
        (a handful of files) this is actually used on. Filtering by score
        alone would silently drop a chunk that's the single best (sometimes
        the ONLY) match for the query."""
        if not self._bm25 or not query or not query.strip():
            return []
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        query_token_set = set(query_tokens)
        scores = self._bm25.get_scores(query_tokens)
        candidates = [
            (self._chunks[i], scores[i])
            for i in range(len(self._chunks))
            if query_token_set & set(self._tokenized_chunks[i])
        ]
        candidates.sort(key=lambda pair: pair[1], reverse=True)
        return candidates[:top_k]
