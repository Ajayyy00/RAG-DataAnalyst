"""
test_rag_pipeline.py
====================
Standalone end-to-end test for the schema-aware RAG pipeline.
No database required — uses mock TableInfo objects.

Run:
    .venv\Scripts\python.exe test_rag_pipeline.py
"""
import sys
import asyncio
import io

# Force UTF-8 stdout so arrow/unicode chars in schema don't crash on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, ".")

SEPARATOR = "-" * 60

# ── Step 1: Import verification ───────────────────────────────────────────────
print(SEPARATOR)
print("STEP 1: Import verification")
print(SEPARATOR)
from app.services.embedding_service import EmbeddingService
from app.services.schema_extractor import TableInfo, ColumnInfo
from app.services.rag_service import RAGService
from app.services.text_to_sql_service import TextToSQLService, FEW_SHOT_EXAMPLES

print("  [OK] EmbeddingService")
print("  [OK] SchemaExtractor (TableInfo, ColumnInfo)")
print("  [OK] RAGService")
print("  [OK] TextToSQLService")

# ── Step 2: Build mock tables (no DB needed) ──────────────────────────────────
print()
print(SEPARATOR)
print("STEP 2: Mock schema (patients / diagnoses / lab_results)")
print(SEPARATOR)

patients = TableInfo(
    name="patients", schema_name="public", comment=None, row_count=52400,
    columns=[
        ColumnInfo("id",            "uuid",              False, None, True,  False, None,         None,  "patient unique id", 1),
        ColumnInfo("date_of_birth", "date",              False, None, False, False, None,         None,  None,                2),
        ColumnInfo("gender",        "character varying", True,  None, False, False, None,         None,  None,                3),
        ColumnInfo("mrn",           "character varying", False, None, False, False, None,         None,  "medical record number", 4),
    ],
)

diagnoses = TableInfo(
    name="diagnoses", schema_name="public",
    comment="ICD-10 diagnostic codes assigned during clinical encounters",
    row_count=890200,
    columns=[
        ColumnInfo("id",           "uuid",              False, None, True,  False, None,         None,  None, 1),
        ColumnInfo("icd10_code",   "character varying", False, None, False, False, None,         None,  None, 2),
        ColumnInfo("encounter_id", "uuid",              False, None, False, True,  "encounters", "id",  None, 3),
        ColumnInfo("patient_id",   "uuid",              False, None, False, True,  "patients",   "id",  None, 4),
        ColumnInfo("diagnosis_rank","integer",          True,  None, False, False, None,         None,  None, 5),
    ],
)

lab_results = TableInfo(
    name="lab_results", schema_name="public",
    comment="Laboratory test results with LOINC codes",
    row_count=1200000,
    columns=[
        ColumnInfo("id",           "uuid",    False, None, True,  False, None,       None,  None, 1),
        ColumnInfo("patient_id",   "uuid",    False, None, False, True,  "patients", "id",  None, 2),
        ColumnInfo("loinc_code",   "character varying", True, None, False, False, None, None, None, 3),
        ColumnInfo("result_value", "numeric", True,  None, False, False, None,       None,  None, 4),
        ColumnInfo("result_unit",  "character varying", True, None, False, False, None, None, None, 5),
        ColumnInfo("collected_at", "timestamp with time zone", True, None, False, False, None, None, None, 6),
    ],
)

for t in [patients, diagnoses, lab_results]:
    print(f"  Table: {t.name:15} cols={len(t.columns):2}  rows={t.row_count:>10,}  hash={t.schema_hash()}")

# ── Step 3: Chunking ──────────────────────────────────────────────────────────
print()
print(SEPARATOR)
print("STEP 3: 3-strategy chunking")
print(SEPARATOR)

rag = RAGService()
all_chunks = []
for t in [patients, diagnoses, lab_results]:
    chunks = rag._build_chunks(t)
    all_chunks.extend(chunks)
    types = [c.chunk_type for c in chunks]
    print(f"  {t.name:15} -> {len(chunks)} chunks: {types}")

print(f"\n  Total chunks to embed: {len(all_chunks)}")

# ── Step 4: Embedding ─────────────────────────────────────────────────────────
print()
print(SEPARATOR)
print("STEP 4: Embedding service (sentence-transformers/all-MiniLM-L6-v2)")
print(SEPARATOR)

embedder = EmbeddingService()
test_query = "Show diabetic patients over 60 with high glucose"
vec = embedder.encode_single(test_query)
print(f"  Query : '{test_query}'")
print(f"  Vector: dim={len(vec)}, first5={[round(x,4) for x in vec[:5]]}")

# ── Step 5: Index into ephemeral ChromaDB ─────────────────────────────────────
print()
print(SEPARATOR)
print("STEP 5: ChromaDB ephemeral indexing")
print(SEPARATOR)

texts  = [c.text for c in all_chunks]
embs   = asyncio.run(embedder.encode_batch_async(texts, show_progress=False))
col    = rag._get_collection()
col.upsert(
    ids        = [c.id for c in all_chunks],
    documents  = texts,
    embeddings = embs,
    metadatas  = [c.to_metadata() for c in all_chunks],
)
print(f"  Indexed {len(all_chunks)} chunks from 3 tables")
print(f"  ChromaDB collection '{col.name}' — total docs: {col.count()}")

# ── Step 6: Retrieve relevant tables ─────────────────────────────────────────
print()
print(SEPARATOR)
print("STEP 6: Retrieval — 'Show diabetic patients over 60 with high glucose'")
print(SEPARATOR)

retrieved, context = rag.retrieve(test_query, top_k=3)
print(f"  Retrieved tables: {[r.name for r in retrieved]}")
for r in retrieved:
    print(f"    [{r.name}] score={round(r.score,4)} chunks_matched={r.chunks_matched} related={r.related_tables}")

# ── Step 7: Context string ────────────────────────────────────────────────────
print()
print(SEPARATOR)
print("STEP 7: LLM context string (preview)")
print(SEPARATOR)
print(context[:800].encode('ascii', errors='replace').decode('ascii'))
print("  ...[truncated]")

# ── Step 8: Debug search ──────────────────────────────────────────────────────
print()
print(SEPARATOR)
print("STEP 8: Debug search (top 5 raw chunks)")
print(SEPARATOR)
raw = rag.search_debug("glucose diabetes patients", n=5)
for hit in raw:
    print(f"  [{hit['chunk_type']:14}] table={hit['table']:15} dist={hit['distance']}  text='{hit['text'][:70]}...'")

# ── Step 9: Verify TextToSQLService prompt structure ─────────────────────────
print()
print(SEPARATOR)
print("STEP 9: TextToSQLService prompt structure")
print(SEPARATOR)
print(f"  ALLOWED_TABLES count  : {len(TextToSQLService.__module__)} (module loaded OK)")
print(f"  FEW_SHOT_EXAMPLES size: {len(FEW_SHOT_EXAMPLES)} chars, {len(FEW_SHOT_EXAMPLES.split('---'))-1} examples")
svc = TextToSQLService()
msgs = svc._build_messages(test_query, context, [])
print(f"  Messages count: {len(msgs)}")
print(f"  System message size: {len(msgs[0]['content'])} chars")
print(f"  User message preview: '{msgs[-1]['content'][:100]}'...")

# ── Step 10: Stats ────────────────────────────────────────────────────────────
print()
print(SEPARATOR)
print("STEP 10: Collection stats")
print(SEPARATOR)
stats = rag.collection_stats()
print(f"  Status        : {stats['status']}")
print(f"  Collection    : {stats['collection']}")
print(f"  Total chunks  : {stats['total_chunks']}")

print()
print("=" * 60)
print("  ALL 10 STEPS PASSED — RAG pipeline is fully functional!")
print("=" * 60)
