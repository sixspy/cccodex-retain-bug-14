import sqlite3

from app.services.partitions import get_partition


def execute_judgment(conn: sqlite3.Connection, judgment_id: int) -> dict:
    """执行单条裁决：归档写入 archive_uri；销毁清空在线态。整单失败则回滚本条。"""
    row = conn.execute(
        "SELECT * FROM judgments WHERE id = ?", (judgment_id,)
    ).fetchone()
    if not row:
        raise ValueError("裁决不存在")
    judgment = dict(row)
    if judgment["status"] not in ("待执行", "已失败"):
        raise ValueError(f"当前状态不可执行：{judgment['status']}")

    part = get_partition(conn, judgment["partition_id"])
    if not part:
        raise ValueError("分区不存在")
    if part["storage_state"] not in ("在线", "裁撤中"):
        raise ValueError(f"分区状态不可裁撤：{part['storage_state']}")

    conn.execute(
        "UPDATE judgments SET status = '执行中', fail_reason = '' WHERE id = ?",
        (judgment_id,),
    )
    conn.execute(
        "UPDATE partitions SET storage_state = '裁撤中' WHERE id = ?",
        (part["id"],),
    )

    action = judgment["decided_action"]
    try:
        if action == "归档":
            uri = f"archive://{part['domain_code']}/{part['biz_date']}"
            conn.execute(
                "UPDATE partitions SET storage_state = '已归档', archive_uri = ? WHERE id = ?",
                (uri, part["id"]),
            )
            result_state = "已归档"
            archive_uri = uri
            detail = "分区已归档并保留可查归档地址"
        elif action == "销毁":
            conn.execute(
                "UPDATE partitions SET storage_state = '已销毁', archive_uri = NULL, "
                "row_count = 0 WHERE id = ?",
                (part["id"],),
            )
            result_state = "已销毁"
            archive_uri = None
            detail = "分区已销毁，在线行数清零"
        else:
            raise ValueError(f"未知动作：{action}")

        conn.execute(
            "UPDATE judgments SET status = '已完成' WHERE id = ?",
            (judgment_id,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO execute_runs "
            "(judgment_id, action, result_state, archive_uri, ok, detail) "
            "VALUES (?,?,?,?,1,?)",
            (judgment_id, action, result_state, archive_uri, detail),
        )
    except Exception as exc:  # noqa: BLE001 — 基线失败闭：恢复在线并记失败
        conn.execute(
            "UPDATE partitions SET storage_state = '在线', archive_uri = NULL WHERE id = ?",
            (part["id"],),
        )
        conn.execute(
            "UPDATE judgments SET status = '已失败', fail_reason = ? WHERE id = ?",
            (str(exc), judgment_id),
        )
        conn.execute(
            "INSERT OR REPLACE INTO execute_runs "
            "(judgment_id, action, result_state, archive_uri, ok, detail) "
            "VALUES (?,?,?,?,0,?)",
            (judgment_id, action, "在线", None, str(exc)),
        )
        raise

    return get_run_by_judgment(conn, judgment_id)


def get_run_by_judgment(conn: sqlite3.Connection, judgment_id: int) -> dict | None:
    row = conn.execute(
        "SELECT id, judgment_id, action, result_state, archive_uri, ok, detail, created_at "
        "FROM execute_runs WHERE judgment_id = ?",
        (judgment_id,),
    ).fetchone()
    return dict(row) if row else None


def list_runs(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, judgment_id, action, result_state, archive_uri, ok, detail, created_at "
        "FROM execute_runs ORDER BY id DESC"
    ).fetchall()
    return [dict(r) for r in rows]
