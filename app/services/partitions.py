import sqlite3


def list_partitions(
    conn: sqlite3.Connection,
    domain_code: str | None = None,
    storage_state: str | None = None,
) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []
    if domain_code:
        clauses.append("domain_code = ?")
        params.append(domain_code)
    if storage_state:
        clauses.append("storage_state = ?")
        params.append(storage_state)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        "SELECT id, domain_code, biz_date, row_count, storage_state, "
        "archive_uri, created_at FROM partitions"
        + where
        + " ORDER BY domain_code, biz_date",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def get_partition(conn: sqlite3.Connection, partition_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, domain_code, biz_date, row_count, storage_state, "
        "archive_uri, created_at FROM partitions WHERE id = ?",
        (partition_id,),
    ).fetchone()
    return dict(row) if row else None
