"""
Knowledge query machine.

Unified interface the agents call when they want a music-theory passage.
Backends — tried in priority order — are:

  1. local_curated   : theory_library.THEORY_ENTRIES keyword search.
                       Always available, zero I/O, instant.
  2. local_rag       : optional embedding-based retrieval over a local
                       corpus (Adler's 'Study of Orchestration',
                       斯波索宾 '和声学', user PDFs). Stubbed by default;
                       enabling it requires the `sentence-transformers`
                       + a vector store (chromadb / lancedb / faiss).
                       The stub returns [] but does not crash.
  3. web_search      : optional Tavily / Serper API for long-tail or
                       current questions. Stubbed by default; caller
                       must set MG_WEB_SEARCH_API_KEY to enable.

The machine is DETERMINISTIC for local_curated (no randomness) and
IDEMPOTENT (calling twice with the same query returns the same answer).
It is safe to call from any agent at any point.

Return shape
------------
All queries return a list of `QueryHit` dataclasses. Agents typically
want the `.passage` field joined with "\\n\\n".
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Iterable, Protocol

from src.knowledge.theory_library import (
    THEORY_ENTRIES,
    TheoryEntry,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class QueryHit:
    """One retrieved knowledge passage."""

    passage: str
    source: str          # "local_curated" | "local_rag" | "web_search"
    title: str = ""
    score: float = 0.0
    entry_id: str = ""   # populated for local_curated
    url: str = ""        # populated for web_search
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Backend protocol
# ---------------------------------------------------------------------------

class _QueryBackend(Protocol):
    """Shared protocol: str -> list[QueryHit]."""

    name: str
    available: bool

    def query(self, question: str, max_results: int) -> list[QueryHit]:
        ...


# ---------------------------------------------------------------------------
# Backend 1: Local curated keyword search
# ---------------------------------------------------------------------------

_WORD_SPLIT = re.compile(r"[\s,./;:!?()\[\]{}\"'<>|\\`~@#$%^&*=+\-—]+")


def _tokenize(text: str) -> list[str]:
    """Cheap tokenizer: lowercase, split on punctuation+whitespace."""
    return [t for t in _WORD_SPLIT.split(text.lower()) if t]


class _LocalCuratedBackend:
    """Keyword search over `theory_library.THEORY_ENTRIES`."""

    name = "local_curated"
    available = True

    def __init__(self, entries: Iterable[TheoryEntry] | None = None):
        self._entries = list(entries) if entries is not None else list(
            THEORY_ENTRIES
        )

    def query(self, question: str, max_results: int) -> list[QueryHit]:
        terms = _tokenize(question)
        if not terms:
            return []
        scored: list[tuple[float, TheoryEntry]] = []
        for e in self._entries:
            s = e.match_score(terms)
            if s > 0:
                scored.append((s, e))
        scored.sort(key=lambda x: (-x[0], x[1].id))
        hits: list[QueryHit] = []
        for score, e in scored[:max_results]:
            hits.append(
                QueryHit(
                    passage=e.body,
                    source=self.name,
                    title=e.title,
                    score=score,
                    entry_id=e.id,
                    tags=list(e.tags),
                )
            )
        return hits


# ---------------------------------------------------------------------------
# Backend 2: Local RAG (stub)
# ---------------------------------------------------------------------------

class _LocalRagBackend:
    """Stub for embedding-based retrieval over a local corpus.

    Real implementation outline (for future work, not enabled here):
      - load `sentence-transformers` (bge-m3 or bge-small-en)
      - embed `theory_library` passages once at module import
      - embed user PDFs via unstructured.io or pdfplumber chunking
      - persist to a local vector store (chromadb / faiss / lancedb)
      - query by cosine similarity; top-k reranked by a cross-encoder
    The stub returns no hits but does not raise, so the machine gracefully
    degrades to local_curated when embeddings are not installed.
    """

    name = "local_rag"

    def __init__(self, index_dir: str | None = None):
        self.index_dir = index_dir
        self.available = False
        # Soft-detect whether embeddings are available. Don't IMPORT the
        # libraries unless the user explicitly enables RAG, so default
        # installs stay lightweight.
        if os.environ.get("MG_ENABLE_LOCAL_RAG") == "1":
            try:
                import importlib  # noqa: F401
                mod = importlib.util.find_spec("sentence_transformers")
                vec = importlib.util.find_spec("chromadb")
                self.available = bool(mod and vec)
            except Exception:
                self.available = False

    def query(self, question: str, max_results: int) -> list[QueryHit]:
        if not self.available:
            return []
        # Deliberate no-op stub. A real implementation would embed `question`,
        # query the vector store, rerank, and build QueryHit objects with
        # source="local_rag".
        logger.info(
            "[KnowledgeQueryMachine] local_rag is enabled but stubbed; "
            "falling back to curated."
        )
        return []


# ---------------------------------------------------------------------------
# Backend 3: Web search (stub)
# ---------------------------------------------------------------------------

class _WebSearchBackend:
    """Stub for a web-search API (Tavily / Serper / Brave Search).

    Enabled only when the user sets MG_WEB_SEARCH_API_KEY + optionally
    MG_WEB_SEARCH_PROVIDER=tavily|serper. The stub returns no hits; a
    real implementation would:
      - build a domain-scoped query ("site:wikipedia.org OR ...")
      - call the provider
      - return top N snippets as QueryHit with source="web_search"

    Legal note: direct scraping of copyrighted sites (e.g. 知乎) is
    out of scope — use official search APIs only.
    """

    name = "web_search"

    def __init__(self):
        self.api_key = os.environ.get("MG_WEB_SEARCH_API_KEY", "")
        self.provider = os.environ.get(
            "MG_WEB_SEARCH_PROVIDER", "tavily",
        )
        self.available = bool(self.api_key)

    def query(self, question: str, max_results: int) -> list[QueryHit]:
        if not self.available:
            return []
        logger.info(
            "[KnowledgeQueryMachine] web_search (%s) is enabled but "
            "stubbed; real API call not yet implemented. "
            "Returning no hits.",
            self.provider,
        )
        return []


# ---------------------------------------------------------------------------
# Public facade
# ---------------------------------------------------------------------------

class MusicKnowledgeQueryMachine:
    """Unified front-door for music-theory knowledge queries.

    Usage (sync):
        km = MusicKnowledgeQueryMachine()
        hits = km.query("pentatonic Chinese arrangement", max_results=3)
        for h in hits:
            print(h.title, h.score, h.source)

    The class is cheap to instantiate (no I/O); feel free to build a
    module-level default via `get_default_machine()`.
    """

    def __init__(
        self,
        curated: _LocalCuratedBackend | None = None,
        rag: _LocalRagBackend | None = None,
        web: _WebSearchBackend | None = None,
    ):
        self.curated = curated or _LocalCuratedBackend()
        self.rag = rag or _LocalRagBackend()
        self.web = web or _WebSearchBackend()

    # --- general query -----------------------------------------------------

    def query(
        self,
        question: str,
        max_results: int = 3,
        include_sources: Iterable[str] | None = None,
    ) -> list[QueryHit]:
        """Return the top `max_results` passages ranked across backends.

        include_sources: subset of {"local_curated","local_rag","web_search"}
        to consult. Default: all available.
        """
        if not question or not question.strip():
            return []
        sources = {
            s.strip().lower() for s in (include_sources or [
                "local_curated", "local_rag", "web_search",
            ])
        }

        merged: list[QueryHit] = []
        if "local_curated" in sources:
            merged.extend(self.curated.query(question, max_results))
        if "local_rag" in sources and self.rag.available:
            merged.extend(self.rag.query(question, max_results))
        if "web_search" in sources and self.web.available:
            merged.extend(self.web.query(question, max_results))

        # Prefer curated hits (score ordering) but allow RAG/web to
        # surface if curated returned nothing.
        if not merged:
            return []
        merged.sort(key=lambda h: (-h.score, h.source, h.title))
        return merged[:max_results]

    # --- convenience wrappers ---------------------------------------------

    def query_for_genre(
        self, genre: str, max_results: int = 3,
    ) -> list[QueryHit]:
        """Return curated hits whose applies_to_genres matches."""
        g = genre.lower().strip()
        hits: list[QueryHit] = []
        for e in THEORY_ENTRIES:
            applies = [x.lower() for x in (e.applies_to_genres or [])]
            if g in applies:
                hits.append(
                    QueryHit(
                        passage=e.body, source="local_curated",
                        title=e.title, score=10.0,
                        entry_id=e.id, tags=list(e.tags),
                    )
                )
        return hits[:max_results]

    def query_for_agent(
        self, agent_name: str, max_results: int = 5,
    ) -> list[QueryHit]:
        """Return curated hits tagged for a specific agent role."""
        a = agent_name.lower().strip()
        hits: list[QueryHit] = []
        for e in THEORY_ENTRIES:
            applies = [x.lower() for x in (e.applies_to_agents or [])]
            if a in applies:
                hits.append(
                    QueryHit(
                        passage=e.body, source="local_curated",
                        title=e.title, score=10.0,
                        entry_id=e.id, tags=list(e.tags),
                    )
                )
        return hits[:max_results]

    def format_hits_for_prompt(
        self, hits: list[QueryHit], header: str = "THEORY CONTEXT",
    ) -> str:
        """Render a list of hits into a compact prompt block."""
        if not hits:
            return ""
        lines: list[str] = [f"{header}:"]
        for h in hits:
            lines.append(f"- [{h.title}] {h.passage}")
        return "\n".join(lines)

    # --- diagnostics -------------------------------------------------------

    def status(self) -> dict:
        """Return a dict describing which backends are live."""
        return {
            "curated": self.curated.available,
            "local_rag": self.rag.available,
            "web_search": self.web.available,
            "rag_env_enabled": os.environ.get(
                "MG_ENABLE_LOCAL_RAG", "0",
            ) == "1",
            "web_env_enabled": bool(
                os.environ.get("MG_WEB_SEARCH_API_KEY", "")
            ),
        }


# ---------------------------------------------------------------------------
# Module-level default singleton
# ---------------------------------------------------------------------------

_DEFAULT_MACHINE: MusicKnowledgeQueryMachine | None = None


def get_default_machine() -> MusicKnowledgeQueryMachine:
    """Return a shared, lazily-built query machine."""
    global _DEFAULT_MACHINE
    if _DEFAULT_MACHINE is None:
        _DEFAULT_MACHINE = MusicKnowledgeQueryMachine()
    return _DEFAULT_MACHINE


# ---------------------------------------------------------------------------
# Convenience top-level helpers the agents can call directly
# ---------------------------------------------------------------------------

def theory_hints_for_request(
    genre: str | None,
    agent_name: str | None = None,
    extra_question: str | None = None,
    max_results: int = 4,
) -> list[str]:
    """Return a list of 1-line passages useful for the given agent/genre.

    Used by prompt builders to inject a compact THEORY CONTEXT block.
    """
    km = get_default_machine()
    hits: list[QueryHit] = []

    if genre:
        hits.extend(km.query_for_genre(genre, max_results=max_results))
    if agent_name:
        # Only add agent-tagged hits not already present by entry_id.
        seen = {h.entry_id for h in hits}
        for h in km.query_for_agent(
            agent_name, max_results=max_results,
        ):
            if h.entry_id not in seen:
                hits.append(h)
                seen.add(h.entry_id)
    if extra_question:
        seen = {h.entry_id for h in hits}
        for h in km.query(extra_question, max_results=max_results):
            if h.entry_id not in seen:
                hits.append(h)
                seen.add(h.entry_id)

    # Keep the prompt block tight — dedupe and cap.
    compact: list[str] = []
    for h in hits[: 2 * max_results]:
        compact.append(f"[{h.title}] {h.passage}")
    return compact[:max_results]
