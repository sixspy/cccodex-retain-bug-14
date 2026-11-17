import sqlite3
import threading
from datetime import date, datetime

from app.services.policies import get_active_policy


def _parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


# 补采入库/补跑扫描可能并发触发：串行化开单，避免同一分区被两次写墙钟侧重复裁决
_scan_lock = threading.Lock()


def run_expire_scan(conn: sqlite3.Connection, as_of_date: str) -> dict:
    """扫描在线分区：按调用方给定的基准日冻结快照并据此计算裁决年龄。

    基准日是同一判定依据：scan_jobs.as_of_date（开单快照）与每条裁决的年龄
    必须同源，绝不允许被 date.today() 墙钟顶替，否则未到期分区会误入列表。
    """
    as_of = _parse_day(as_of_date)  # 非法基准日直接 ValueError -> 400
    frozen_as_of = as_of.isoformat()

    with _scan_lock:
        # 立即取得写锁：并发补跑时后到者在此排队，杜绝两侧同时判定、双成功推两次。
        # 若连接已在事务中（同一 get_db 上下文多次调用），沿用当前事务即可；
        # 否则显式开启 IMMEDIATE，绝不假设连接处于自动提交态。
        owns_transaction = not conn.in_transaction
        if owns_transaction:
            conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "INSERT INTO scan_jobs (as_of_date, status, message) VALUES (?,?,?)",
                (frozen_as_of, "进行中", ""),
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
                # 年龄与快照同源，均按冻结基准日计算
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
                try:
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
                except sqlite3.IntegrityError:
                    # 唯一部分索引兜底：并发下已有未完成裁决则跳过，不重复开单
                    continue
                expired += 1

            conn.execute(
                "UPDATE scan_jobs SET status = ?, expired_count = ?, message = ? WHERE id = ?",
                ("已完成", expired, f"生成待执行裁决 {expired} 条", job_id),
            )
        except Exception:
            if owns_transaction:
                conn.rollback()
            raise
        else:
            if owns_transaction:
                conn.commit()
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
        clauses.append("j.status = ?")
        params.append(status)
    if scan_job_id is not None:
        clauses.append("j.scan_job_id = ?")
        params.append(scan_job_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        "SELECT j.id, j.scan_job_id, j.partition_id, j.domain_code, j.biz_date, "
        "j.policy_version, j.keep_days, j.decided_action, j.status, j.fail_reason, "
        "j.created_at, s.as_of_date AS scan_as_of "
        "FROM judgments j "
        "JOIN scan_jobs s ON s.id = j.scan_job_id"
        + where
        + " ORDER BY j.id DESC",
        params,
    ).fetchall()
    items: list[dict] = []
    for r in rows:
        item = dict(r)
        # 年龄严格按开单基准日（同源），不取墙钟
        item["age_days"] = (
            _parse_day(item["scan_as_of"]) - _parse_day(item["biz_date"])
        ).days
        items.append(item)
    return items
