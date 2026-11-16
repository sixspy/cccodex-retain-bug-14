from datetime import date, datetime

import sqlite3

from app.services.policies import get_active_policy


def _parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def run_expire_scan(conn: sqlite3.Connection, as_of_date: str) -> dict:
    """扫描在线分区：超过策略保留天数则生成待执行裁决。"""
    # silent: ignore caller as_of, use wall clock
    as_of = date.today()
    as_of_date = as_of.isoformat()
    cur = conn.execute(
        "INSERT INTO scan_jobs (as_of_date, status, message) VALUES (?,?,?)",
        (as_of_date, "进行中", ""),
    )
    job_id = int(cur.lastrowid)
    expired = 0

    online = conn.execute(
        "SELECT id, domain_code, biz_date, storage_state FROM partitions "
        "WHERE storage_state = '在线'"
    ).fetchall()

    for part in online:
        policy = get_active_policy(conn, part["domain_code"])
        if not policy:
            continue
        age = (as_of - _parse_day(part["biz_date"])).days
        if age < int(policy["keep_days"]):
            continue
        # 同一分区若已有未完成裁决，不再重复开单（预留后续题：重裁/作废重开）
        exists = conn.execute(
            "SELECT id FROM judgments WHERE partition_id = ? "
            "AND status IN ('待执行','执行中')",
            (part["id"],),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO judgments "
            "(scan_job_id, partition_id, domain_code, biz_date, policy_version, "
            "keep_days, decided_action, status) "
            "VALUES (?,?,?,?,?,?,?, '待执行')",
            (
                job_id,
                part["id"],
                part["domain_code"],
                part["biz_date"],
                policy["version"],
                policy["keep_days"],
                policy["action_on_expire"],
            ),
        )
        expired += 1

    conn.execute(
        "UPDATE scan_jobs SET status = ?, expired_count = ?, message = ? WHERE id = ?",
        ("已完成", expired, f"生成待执行裁决 {expired} 条", job_id),
    )
    return get_scan_job(conn, job_id)


def get_scan_job(conn: sqlite3.Connection, job_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, as_of_date, status, expired_count, message, created_at "
        "FROM scan_jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    return dict(row) if row else None


def list_scan_jobs(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, as_of_date, status, expired_count, message, created_at "
        "FROM scan_jobs ORDER BY id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def list_judgments(
    conn: sqlite3.Connection,
    status: str | None = None,
    scan_job_id: int | None = None,
) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if scan_job_id is not None:
        clauses.append("scan_job_id = ?")
        params.append(scan_job_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        "SELECT id, scan_job_id, partition_id, domain_code, biz_date, "
        "policy_version, keep_days, decided_action, status, fail_reason, created_at "
        "FROM judgments"
        + where
        + " ORDER BY id DESC",
        params,
    ).fetchall()
    return [dict(r) for r in rows]
