"""
rag_service.py  (complete rewrite)
===================================
Schema-aware RAG pipeline:

  INDEXING
  --------
  1. SchemaExtractor pulls rich metadata from PostgreSQL.
  2. Three chunk types are created per table:
       • "table"        — full natural-language description  (best for matching topics)
       • "columns"      — per-column type+meaning text       (best for column-level queries)
       • "relationship" — FK join sentences                   (best for JOIN-heavy queries)
  3. Each chunk is embedded via EmbeddingService and upserted into ChromaDB.
  4. A schema fingerprint (SHA-256 of column signatures) is stored in ChromaDB
     metadata so unchanged tables are skipped on subsequent startup calls.

  RETRIEVAL
  ---------
  1. User query is embedded.
  2. ChromaDB is queried with n_results = top_k * 3 (over-fetch, then re-rank).
  3. Results are grouped by table; each table is scored by its best chunk score.
  4. Top-N unique tables are selected.
  5. Full DDL + markdown schema for those tables is returned as a structured
     context string, ready to be injected into the LLM system prompt.

  CONTEXT FORMAT (returned to TextToSQLService)
  ----------------------------------------------
  The context string has three sections:
    § RETRIEVED TABLES  — markdown schema sections (column types, comments, PKs/FKs)
    § DDL               — CREATE TABLE statements (for models that prefer SQL syntax)
    § JOIN HINTS        — FK relationship sentences

  RESILIENCE
  ----------
  • All ChromaDB and embedding errors are caught; retrieval falls back gracefully.
  • Indexing is non-fatal; the application starts even if ChromaDB is down.
  • ChromaDB mode (ephemeral/persistent/http) is controlled via CHROMADB_MODE env var.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional

import chromadb
import structlog
from chromadb.config import Settings as ChromaSettings
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.embedding_service import EmbeddingService
from app.services.schema_extractor import SchemaExtractor, TableInfo

log = structlog.get_logger(__name__)
settings = get_settings()


# ── Chunk types ────────────────────────────────────────────────────────────────
CHUNK_TABLE        = "table"
CHUNK_COLUMNS      = "columns"
CHUNK_RELATIONSHIP = "relationship"


@dataclass
class SchemaChunk:
    """A single unit of schema text to embed and store in ChromaDB."""
    id: str
    text: str
    chunk_type: str
    table_name: str
    schema_hash: str
    related_tables: list[str]

    def to_metadata(self) -> dict[str, Any]:
        return {
            "chunk_type":    self.chunk_type,
            "table_name":    self.table_name,
            "schema_hash":   self.schema_hash,
            "related_tables": json.dumps(self.related_tables),
        }


@dataclass
class RetrievedTable:
    """A table selected by the retrieval step, with its ranking score."""
    name: str
    score: float           # lower = better (cosine distance)
    chunks_matched: int
    related_tables: list[str]
    table_info: Optional[TableInfo] = None


# ── RAGService ─────────────────────────────────────────────────────────────────

class RAGService:
    """
    Full schema-aware RAG pipeline.

    Instantiated once at startup for indexing (async); instantiated per-request
    for retrieval (synchronous ChromaDB query, non-blocking in practice).
    """

    def __init__(self) -> None:
        self._chroma_client: Optional[Any]    = None
        self._collection: Optional[Any]       = None
        self._embedder: Optional[EmbeddingService] = None

    # ── ChromaDB initialisation ────────────────────────────────────────────────

    def _get_client(self) -> Any:
        if self._chroma_client is None:
            mode = settings.chromadb_mode
            if mode == "ephemeral":
                self._chroma_client = chromadb.EphemeralClient(
                    settings=ChromaSettings(anonymized_telemetry=False)
                )
                log.info("ChromaDB: ephemeral in-process mode")
            elif mode == "persistent":
                self._chroma_client = chromadb.PersistentClient(
                    path="./.chromadb_data",
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                log.info("ChromaDB: persistent local-file mode")
            else:
                self._chroma_client = chromadb.HttpClient(
                    host=settings.chromadb_host,
                    port=settings.chromadb_port,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                log.info(
                    "ChromaDB: HTTP client",
                    host=settings.chromadb_host,
                    port=settings.chromadb_port,
                )
        return self._chroma_client

    def _get_collection(self) -> Any:
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name=settings.chromadb_collection,
                metadata={
                    "hnsw:space": "cosine",          # cosine distance for similarity
                    "hnsw:construction_ef": 200,      # higher = better index quality
                    "hnsw:M": 16,                     # HNSW graph connectivity
                },
            )
        return self._collection

    def _get_embedder(self) -> EmbeddingService:
        if self._embedder is None:
            self._embedder = EmbeddingService()
        return self._embedder

    # ── Indexing ───────────────────────────────────────────────────────────────

    async def index_schema(self, db: Optional[AsyncSession] = None, force: bool = False) -> dict:
        """
        Extract schema from PostgreSQL and upsert into ChromaDB.

        Returns a summary dict: {indexed, skipped, total_chunks}.

        Args:
            db:    Optional AsyncSession. If None, a new session is created.
            force: If True, re-index all tables even if unchanged.
        """
        if db is None:
            async with AsyncSessionLocal() as db:
                return await self._do_index(db, force)
        return await self._do_index(db, force)

    async def _do_index(self, db: AsyncSession, force: bool) -> dict:
        extractor = SchemaExtractor(db)
        try:
            tables = await extractor.extract_all()
        except Exception as exc:
            log.error("Schema extraction failed", error=str(exc))
            return {"indexed": 0, "skipped": 0, "total_chunks": 0, "error": str(exc)}

        if not tables:
            log.warning("No tables extracted — ChromaDB not updated")
            return {"indexed": 0, "skipped": 0, "total_chunks": 0}

        collection = self._get_collection()
        existing_hashes = self._fetch_existing_hashes(collection)

        chunks_to_add: list[SchemaChunk] = []
        indexed_tables: list[str]        = []
        skipped_tables: list[str]        = []

        for table in tables:
            table_hash = table.schema_hash()

            # Skip tables whose schema hasn't changed (unless force=True)
            if not force and existing_hashes.get(table.name) == table_hash:
                skipped_tables.append(table.name)
                log.debug("Schema unchanged — skipping", table=table.name)
                continue

            table_chunks = self._build_chunks(table)
            chunks_to_add.extend(table_chunks)
            indexed_tables.append(table.name)

        if not chunks_to_add:
            log.info(
                "All schema hashes match — no re-indexing needed",
                skipped=len(skipped_tables),
            )
            return {
                "indexed": 0,
                "skipped": len(skipped_tables),
                "total_chunks": 0,
                "skipped_tables": skipped_tables,
            }

        # Batch embed all chunks (async to avoid blocking)
        texts      = [c.text for c in chunks_to_add]
        embedder   = self._get_embedder()
        embeddings = await embedder.encode_batch_async(texts, show_progress=True)

        # Upsert into ChromaDB (replaces existing docs with same ID)
        collection.upsert(
            ids        = [c.id for c in chunks_to_add],
            documents  = texts,
            embeddings = embeddings,
            metadatas  = [c.to_metadata() for c in chunks_to_add],
        )

        log.info(
            "Schema indexed",
            indexed_tables=indexed_tables,
            skipped_tables=skipped_tables,
            total_chunks=len(chunks_to_add),
        )
        return {
            "indexed":        len(indexed_tables),
            "skipped":        len(skipped_tables),
            "total_chunks":   len(chunks_to_add),
            "indexed_tables": indexed_tables,
            "skipped_tables": skipped_tables,
        }

    def _build_chunks(self, table: TableInfo) -> list[SchemaChunk]:
        """Create the three chunk types for one table."""
        chunks: list[SchemaChunk] = []
        h = table.schema_hash()

        # 1. Table-level description (for topic-level matching)
        chunks.append(SchemaChunk(
            id            = f"schema__{table.name}__table",
            text          = table.to_description(),
            chunk_type    = CHUNK_TABLE,
            table_name    = table.name,
            schema_hash   = h,
            related_tables= table.related_tables,
        ))

        # 2. Column text (for column-name / type matching)
        col_text = (
            f"Columns of table {table.name}: "
            + "; ".join(c.to_text() for c in table.columns)
        )
        chunks.append(SchemaChunk(
            id            = f"schema__{table.name}__columns",
            text          = col_text,
            chunk_type    = CHUNK_COLUMNS,
            table_name    = table.name,
            schema_hash   = h,
            related_tables= table.related_tables,
        ))

        # 3. Relationship text (for JOIN-path matching) — only if FKs exist
        rel_text = table.to_relationship_text()
        if rel_text:
            chunks.append(SchemaChunk(
                id            = f"schema__{table.name}__relationship",
                text          = rel_text,
                chunk_type    = CHUNK_RELATIONSHIP,
                table_name    = table.name,
                schema_hash   = h,
                related_tables= table.related_tables,
            ))

        return chunks

    @staticmethod
    def _fetch_existing_hashes(collection: Any) -> dict[str, str]:
        """Return {table_name: schema_hash} for all table-type chunks in ChromaDB."""
        try:
            result = collection.get(
                where={"chunk_type": {"$eq": CHUNK_TABLE}},
                include=["metadatas"],
            )
            hashes: dict[str, str] = {}
            for meta in result.get("metadatas", []):
                if meta:
                    hashes[meta["table_name"]] = meta.get("schema_hash", "")
            return hashes
        except Exception:
            return {}

    # ── Retrieval ──────────────────────────────────────────────────────────────

    def retrieve(
        self,
        question: str,
        top_k: Optional[int] = None,
        include_relationships: bool = True,
    ) -> tuple[list[RetrievedTable], str]:
        """
        Embed the question and retrieve the most relevant tables.

        Returns:
            (retrieved_tables, context_string)

            context_string is the full formatted schema context for the LLM.
        """
        k = top_k or settings.rag_top_k
        over_fetch = min(k * 3, 20)  # over-fetch then re-rank by table

        try:
            embedder = self._get_embedder()
            query_vec = embedder.encode_single(question)
            collection = self._get_collection()

            results = collection.query(
                query_embeddings=[query_vec],
                n_results=over_fetch,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            log.error("ChromaDB retrieval failed", error=str(exc))
            return [], ""

        # Re-rank: score each table by its best chunk distance
        table_scores: dict[str, float]        = {}
        table_chunks: dict[str, int]          = {}
        table_related: dict[str, list[str]]   = {}

        docs      = results.get("documents",  [[]])[0]
        metas     = results.get("metadatas",  [[]])[0]
        distances = results.get("distances",  [[]])[0]

        for doc, meta, dist in zip(docs, metas, distances):
            if not meta:
                continue
            tname = meta.get("table_name", "")
            if not tname:
                continue

            # Lower distance = higher relevance
            if tname not in table_scores or dist < table_scores[tname]:
                table_scores[tname] = dist

            table_chunks[tname]  = table_chunks.get(tname, 0) + 1
            table_related[tname] = json.loads(meta.get("related_tables", "[]"))

        # Sort by score ascending (closest = most relevant)
        ranked = sorted(table_scores.items(), key=lambda x: x[1])[:k]

        retrieved: list[RetrievedTable] = []
        for tname, score in ranked:
            retrieved.append(RetrievedTable(
                name           = tname,
                score          = score,
                chunks_matched = table_chunks.get(tname, 0),
                related_tables = table_related.get(tname, []),
            ))

        # Expand with implicit related tables not already included
        all_names    = {r.name for r in retrieved}
        extras: set[str] = set()
        for r in retrieved:
            for rel in r.related_tables:
                if rel not in all_names:
                    extras.add(rel)

        log.info(
            "Schema retrieved",
            question_preview=question[:60],
            retrieved=[r.name for r in retrieved],
            auto_expanded=list(extras),
        )

        context = self._format_context(retrieved, extras, include_relationships)
        return retrieved, context

    def retrieve_schema_context(
        self,
        question: str,
        top_k: Optional[int] = None,
    ) -> str:
        """
        Convenience method matching the original API signature.
        Returns only the context string (for backward compatibility with chat.py).
        """
        _, context = self.retrieve(question, top_k=top_k)
        return context

    # ── Context formatting ─────────────────────────────────────────────────────

    def _format_context(
        self,
        primary: list[RetrievedTable],
        extras: set[str],
        include_relationships: bool,
    ) -> str:
        """
        Build the structured schema context string for the LLM.

        Layout:
          RETRIEVED TABLES (markdown) ← primary focus for the LLM
          DDL                          ← fallback / double-check reference
          JOIN HINTS                   ← FK paths for multi-table queries
        """
        # Fetch full metadata from ChromaDB for all needed tables
        all_names = [r.name for r in primary] + list(extras)
        table_docs = self._fetch_table_docs(all_names)

        sections: list[str] = []

        # ── Section 1: Markdown schema ──────────────────────────────────────────
        sections.append("## Relevant Schema\n")
        sections.append(
            "The following tables are most relevant to the user's question. "
            "Use ONLY these tables in your SQL query.\n"
        )
        for r in primary:
            doc = table_docs.get(r.name)
            if doc:
                sections.append(doc)
                sections.append("")

        if extras:
            sections.append("### Supporting tables (via foreign key relationships)\n")
            for name in sorted(extras):
                doc = table_docs.get(name)
                if doc:
                    sections.append(doc)
                    sections.append("")

        # ── Section 2: DDL ─────────────────────────────────────────────────────
        ddl_chunks = self._fetch_ddl_chunks(all_names)
        if ddl_chunks:
            sections.append("## DDL Reference\n```sql")
            sections.extend(ddl_chunks)
            sections.append("```\n")

        # ── Section 3: JOIN hints ───────────────────────────────────────────────
        if include_relationships:
            rel_lines = self._fetch_relationship_chunks(all_names)
            if rel_lines:
                sections.append("## Join Paths\n")
                sections.extend(f"- {r}" for r in rel_lines)

        return "\n".join(sections)

    def _fetch_table_docs(self, table_names: list[str]) -> dict[str, str]:
        """Retrieve stored table-type documents from ChromaDB by table name."""
        if not table_names:
            return {}
        try:
            collection = self._get_collection()
            result = collection.get(
                where={"$and": [
                    {"chunk_type": {"$eq": CHUNK_TABLE}},
                    {"table_name": {"$in": table_names}},
                ]},
                include=["documents", "metadatas"],
            )
            docs: dict[str, str] = {}
            for doc, meta in zip(
                result.get("documents", []),
                result.get("metadatas", []),
            ):
                if meta and doc:
                    docs[meta["table_name"]] = doc
            return docs
        except Exception as exc:
            log.warning("Failed to fetch table docs", error=str(exc))
            return {}

    def _fetch_ddl_chunks(self, table_names: list[str]) -> list[str]:
        """Retrieve column-type chunks to reconstruct DDL hints."""
        if not table_names:
            return []
        try:
            collection = self._get_collection()
            result = collection.get(
                where={"$and": [
                    {"chunk_type": {"$eq": CHUNK_COLUMNS}},
                    {"table_name": {"$in": table_names}},
                ]},
                include=["documents"],
            )
            return result.get("documents", [])
        except Exception:
            return []

    def _fetch_relationship_chunks(self, table_names: list[str]) -> list[str]:
        """Retrieve FK relationship chunks for included tables."""
        if not table_names:
            return []
        try:
            collection = self._get_collection()
            result = collection.get(
                where={"$and": [
                    {"chunk_type": {"$eq": CHUNK_RELATIONSHIP}},
                    {"table_name": {"$in": table_names}},
                ]},
                include=["documents"],
            )
            return result.get("documents", [])
        except Exception:
            return []

    # ── Utility ────────────────────────────────────────────────────────────────

    def collection_stats(self) -> dict:
        """Return collection metadata for health-check endpoint."""
        try:
            col = self._get_collection()
            count = col.count()
            return {"status": "ok", "total_chunks": count, "collection": settings.chromadb_collection}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def search_debug(self, query: str, n: int = 10) -> list[dict]:
        """Return raw retrieval results for the /rag/search debug endpoint."""
        try:
            embedder = self._get_embedder()
            vec      = embedder.encode_single(query)
            col      = self._get_collection()
            results  = col.query(
                query_embeddings=[vec],
                n_results=n,
                include=["documents", "metadatas", "distances"],
            )
            output = []
            for doc, meta, dist in zip(
                results.get("documents",  [[]])[0],
                results.get("metadatas",  [[]])[0],
                results.get("distances",  [[]])[0],
            ):
                output.append({
                    "table":     meta.get("table_name") if meta else None,
                    "chunk_type":meta.get("chunk_type") if meta else None,
                    "distance":  round(dist, 4),
                    "text":      doc[:200] if doc else None,
                })
            return output
        except Exception as exc:
            log.error("Debug search failed", error=str(exc))
            return []
