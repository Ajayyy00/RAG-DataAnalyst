"""Singleton Neo4j async driver with graceful lifecycle management."""
import structlog
from neo4j import AsyncGraphDatabase, AsyncDriver
from app.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

_driver: AsyncDriver | None = None

async def get_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )
        log.info("Neo4j driver initialised", uri=settings.neo4j_uri)
    return _driver


async def close_driver():
    global _driver
    if _driver:
        await _driver.close()
        _driver = None
        log.info("Neo4j driver closed")


from neo4j.graph import Node, Relationship, Path

async def serialize_record(record):
    out = {}
    for key, value in record.items():
        if isinstance(value, Node):
            out[key] = {
                "id": value.element_id,
                "labels": list(value.labels),
                "properties": dict(value)
            }
        elif isinstance(value, Relationship):
            out[key] = {
                "id": value.element_id,
                "type": value.type,
                "start_node_id": value.start_node.element_id,
                "end_node_id": value.end_node.element_id,
                "properties": dict(value)
            }
        elif isinstance(value, Path):
            # Paths are just iterables of relationships and nodes
            out[key] = []
            for item in value:
                if isinstance(item, Node):
                    out[key].append({
                        "id": item.element_id,
                        "labels": list(item.labels),
                        "properties": dict(item)
                    })
                elif isinstance(item, Relationship):
                    out[key].append({
                        "id": item.element_id,
                        "type": item.type,
                        "start_node_id": item.start_node.element_id,
                        "end_node_id": item.end_node.element_id,
                        "properties": dict(item)
                    })
        else:
            out[key] = value
    return out

async def run_query(cypher: str, params: dict = None):
    """Convenience helper — runs a single Cypher query and returns serialized records."""
    driver = await get_driver()
    async with driver.session() as session:
        result = await session.run(cypher, params or {})
        records = await result.fetch(100)
        return [await serialize_record(rec) for rec in records]
