import sqlite3
from datetime import datetime


def _parse_day(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def list_partitions(
    conn: sqlite3.Connection,
    domain_code: str | None = None,
    storage_state: str | None = None,
    as_of_date: str | None = None,
) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []
    if domain_code:
        clauses.append("p.domain_code = ?")
        params.append(domain_code)
    if storage_state:
        clauses.append("p.storage_state = ?")
        params.append(storage_state)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        "SELECT p.id, p.domain_code, p.biz_date, p.row_count, p.storage_state, "
        "p.archive_uri, p.created_at, rp.keep_days, rp.action_on_expire "
        "FROM partitions p "
        "LEFT JOIN retain_policies rp "
        "  ON rp.domain_code = p.domain_code AND rp.active = 1 "
        + where
        + " ORDER BY p.domain_code, p.biz_date",
        params,
    ).fetchall()
    items = [dict(r) for r in rows]

    # 年龄/到期态一律按页面选定基准日核算，绑定基准日而非墙钟
    if as_of_date:
        as_of = _parse_day(as_of_date)
        for item in items:
            item["as_of_date"] = as_of.isoformat()
            item["age_days"] = (as_of - _parse_day(item["biz_date"])).days
            keep = item["keep_days"]
            if keep is None:
                item["due_for_expire"] = False
                item["due_reason"] = "无现行策略"
            else:
                item["due_for_expire"] = item["age_days"] >= int(keep)
                item["due_reason"] = (
                    f"年龄{item['age_days']}天 / 保留{int(keep)}天"
                )
    return items


def get_partition(conn: sqlite3.Connection, partition_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, domain_code, biz_date, row_count, storage_state, "
        "archive_uri, created_at FROM partitions WHERE id = ?",
        (partition_id,),
    ).fetchone()
    return dict(row) if row else None
