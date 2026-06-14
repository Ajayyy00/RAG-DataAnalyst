"""
scripts/index_schema.py
========================
Standalone CLI script for schema indexing.

Usage:
    # From backend/ directory:
    python -m app.scripts.index_schema

    # Force full re-index (ignores hashes):
    python -m app.scripts.index_schema --force

    # Just print what would be indexed (dry run):
    python -m app.scripts.index_schema --dry-run

    # Show collection stats only:
    python -m app.scripts.index_schema --stats

Output format:
    [17 tables found]
    ✓ patients         → 3 chunks  (8 columns, ~52,400 rows)
    ✓ encounters       → 3 chunks  (14 columns, ~310,800 rows)
    ~ diagnoses        → skipped (schema unchanged)
    ...
    ─────────────────────────────────────────────────
    Total: 12 indexed · 5 skipped · 36 chunks stored
    ChromaDB collection: healthcare_schema (36 chunks total)
    Completed in 4.2s
"""

from __future__ import annotations

import argparse
import asyncio

# Suppress noisy startup logs from ML libs
import logging
import time

import structlog

logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)


async def run(force: bool, dry_run: bool, stats_only: bool) -> None:
    from app.config import get_settings
    from app.core.logging import setup_logging
    from app.db.session import AsyncSessionLocal
    from app.services.rag_service import RAGService
    from app.services.schema_extractor import SchemaExtractor

    settings = get_settings()
    setup_logging(settings.log_level)

    rag = RAGService()

    # ── Stats only ─────────────────────────────────────────────────────────────
    if stats_only:
        stats = rag.collection_stats()
        if stats["status"] == "ok":
            print(f"\nChromaDB collection: {stats['collection']}")
            print(f"Total indexed chunks: {stats['total_chunks']}")
        else:
            print(f"\nChromaDB error: {stats['error']}")
        return

    # ── Dry run — just extract, don't index ────────────────────────────────────
    if dry_run:
        print("\n[DRY RUN] Extracting schema from PostgreSQL...\n")
        async with AsyncSessionLocal() as db:
            extractor = SchemaExtractor(db)
            tables = await extractor.extract_all()

        print(f"[{len(tables)} tables found]\n")
        for t in tables:
            col_names = ", ".join(c.name for c in t.columns[:5])
            more = f" +{len(t.columns) - 5} more" if len(t.columns) > 5 else ""
            print(
                f"  {t.name:<22} "
                f"{len(t.columns):>2} cols  "
                f"~{t.row_count:>10,} rows  "
                f"[{col_names}{more}]"
            )
        print(f"\n{len(tables)} tables would be indexed.")
        return

    # ── Full index ─────────────────────────────────────────────────────────────
    print(f"\nHealthCopilot — Schema Indexer")
    print(f"ChromaDB mode : {settings.chromadb_mode}")
    print(f"Embedding model: {settings.embedding_model}")
    print(f"Force re-index : {force}")
    print("─" * 56)

    t0 = time.perf_counter()

    async with AsyncSessionLocal() as db:
        extractor = SchemaExtractor(db)
        tables = await extractor.extract_all()
        print(f"[{len(tables)} tables found]\n")

        result = await rag.index_schema(db=db, force=force)

    elapsed = time.perf_counter() - t0

    # Pretty print results
    indexed_set = set(result.get("indexed_tables", []))
    skipped_set = set(result.get("skipped_tables", []))

    for t in tables:
        status_sym = "✓" if t.name in indexed_set else "~"
        status_txt = (
            f"{result['total_chunks'] // max(len(indexed_set), 1)} chunks"
            if t.name in indexed_set
            else "skipped (schema unchanged)"
        )
        print(f"  {status_sym} {t.name:<22} → {status_txt}")

    print("\n" + "─" * 56)
    print(
        f"Total: {result['indexed']} indexed · "
        f"{result['skipped']} skipped · "
        f"{result['total_chunks']} chunks stored"
    )

    # Show collection total
    stats = rag.collection_stats()
    if stats["status"] == "ok":
        print(
            f"ChromaDB collection: {stats['collection']} ({stats['total_chunks']} chunks total)"
        )

    print(f"Completed in {elapsed:.1f}s\n")

    if result.get("error"):
        print(f"⚠  Error during indexing: {result['error']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index PostgreSQL schema into ChromaDB"
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-index all tables regardless of hash"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be indexed without writing",
    )
    parser.add_argument(
        "--stats", action="store_true", help="Show ChromaDB collection stats and exit"
    )
    args = parser.parse_args()

    asyncio.run(run(force=args.force, dry_run=args.dry_run, stats_only=args.stats))


if __name__ == "__main__":
    main()
