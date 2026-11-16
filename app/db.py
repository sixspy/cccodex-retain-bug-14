import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import Config


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or Config.database()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db(db_path: str | None = None):
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS retain_policies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain_code TEXT NOT NULL,
  domain_name TEXT NOT NULL,
  keep_days INTEGER NOT NULL,
  action_on_expire TEXT NOT NULL CHECK (action_on_expire IN ('归档','销毁')),
  version INTEGER NOT NULL DEFAULT 1,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(domain_code, version)
);

CREATE TABLE IF NOT EXISTS partitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain_code TEXT NOT NULL,
  biz_date TEXT NOT NULL,
  row_count INTEGER NOT NULL DEFAULT 0,
  storage_state TEXT NOT NULL CHECK (
    storage_state IN ('在线','已归档','已销毁','裁撤中')
  ),
  archive_uri TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(domain_code, biz_date)
);

CREATE TABLE IF NOT EXISTS scan_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  as_of_date TEXT NOT NULL,
  status TEXT NOT NULL,
  expired_count INTEGER NOT NULL DEFAULT 0,
  message TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS judgments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_job_id INTEGER NOT NULL,
  partition_id INTEGER NOT NULL,
  domain_code TEXT NOT NULL,
  biz_date TEXT NOT NULL,
  policy_version INTEGER NOT NULL,
  keep_days INTEGER NOT NULL,
  decided_action TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('待执行','执行中','已完成','已失败','已作废')),
  fail_reason TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(scan_job_id) REFERENCES scan_jobs(id),
  FOREIGN KEY(partition_id) REFERENCES partitions(id)
);

CREATE TABLE IF NOT EXISTS execute_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  judgment_id INTEGER NOT NULL UNIQUE,
  action TEXT NOT NULL,
  result_state TEXT NOT NULL,
  archive_uri TEXT,
  ok INTEGER NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(judgment_id) REFERENCES judgments(id)
);

CREATE TABLE IF NOT EXISTS reconcile_reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  as_of_date TEXT NOT NULL,
  online_count INTEGER NOT NULL,
  archived_count INTEGER NOT NULL,
  destroyed_count INTEGER NOT NULL,
  pending_judgment_count INTEGER NOT NULL,
  mismatch_count INTEGER NOT NULL,
  summary TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


SEED_POLICIES = [
    ("orders", "订单明细域", 7, "归档"),
    ("payments", "支付流水域", 14, "归档"),
    ("events", "埋点事件域", 3, "销毁"),
    ("inventory", "库存快照域", 10, "归档"),
]

SEED_PARTITIONS = [
    ("orders", "2026-11-01", 1200, "在线"),
    ("orders", "2026-11-05", 980, "在线"),
    ("orders", "2026-11-10", 1100, "在线"),
    ("orders", "2026-11-14", 1050, "在线"),
    ("payments", "2026-10-20", 800, "在线"),
    ("payments", "2026-11-01", 760, "在线"),
    ("payments", "2026-11-12", 790, "在线"),
    ("events", "2026-11-08", 5000, "在线"),
    ("events", "2026-11-12", 5200, "在线"),
    ("events", "2026-11-15", 5100, "在线"),
    ("inventory", "2026-10-30", 300, "在线"),
    ("inventory", "2026-11-11", 310, "在线"),
]


def init_db(db_path: str | None = None) -> None:
    with get_db(db_path) as conn:
        conn.executescript(SCHEMA)
        n = conn.execute("SELECT COUNT(*) AS c FROM retain_policies").fetchone()["c"]
        if n == 0:
            for domain_code, domain_name, keep_days, action in SEED_POLICIES:
                conn.execute(
                    "INSERT INTO retain_policies "
                    "(domain_code, domain_name, keep_days, action_on_expire, version, active) "
                    "VALUES (?,?,?,?,1,1)",
                    (domain_code, domain_name, keep_days, action),
                )
            for domain_code, biz_date, row_count, state in SEED_PARTITIONS:
                conn.execute(
                    "INSERT INTO partitions "
                    "(domain_code, biz_date, row_count, storage_state) "
                    "VALUES (?,?,?,?)",
                    (domain_code, biz_date, row_count, state),
                )
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('lab_name', ?)",
                (Config.LAB_NAME,),
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('skeleton', ?)",
                (
                    "分区留存策略版本→到期扫描裁决→归档或销毁执行→策略与实物分区对账",
                ),
            )
