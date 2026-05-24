import asyncpg
import types

async def build_resolution_graph(
    pool: asyncpg.Pool,
    template_name: str,
) -> types.MappingProxyType[str, str]:
    """Build the immutable canonical-key→raw-value resolution graph for a template.

    Queries PostgreSQL to produce a dict of all placeholder key-value pairs defined
    by the template's linked content blocks. Keys are uppercased canonical strings.
    When multiple content blocks define the same key, the first by content_block_details.id
    (link order) wins; subsequent duplicates are silently discarded.

    Args:
        pool: Active asyncpg connection pool.
        template_name: The template's ``name`` column value (exact match, case-sensitive).

    Returns:
        An immutable MappingProxyType mapping canonical keys to raw values.
        Raw values may contain ##PLACEHOLDER## tokens for recursive resolution.

    Raises:
        ValueError: If ``template_name`` is not found in the database.
        asyncpg.PostgresError: On any database error.
    """
    async with pool.acquire() as conn:
        # Check if template exists
        template_id = await conn.fetchval(
            "SELECT id FROM template WHERE name = $1", 
            template_name
        )
        if template_id is None:
            raise ValueError(f"Template not found: {template_name!r}")

        # Fetch KV pairs
        query = """
            SELECT DISTINCT ON (kv.field_key) kv.field_key, kv.field_value
            FROM template t
            JOIN template_content_block tcb ON tcb.template_id = t.id
            JOIN content_block cb           ON cb.id = tcb.content_block_id
            JOIN content_block_details cbd  ON cbd.content_block_id = cb.id
            JOIN content_block_kv kv        ON kv.content_block_details_id = cbd.id
            WHERE t.name = $1
            ORDER BY kv.field_key, cbd.id ASC
        """
        rows = await conn.fetch(query, template_name)

        # Build dictionary, ensuring keys are uppercase (canonical format)
        graph_dict = {
            row["field_key"].upper(): row["field_value"]
            for row in rows
        }

        return types.MappingProxyType(graph_dict)
