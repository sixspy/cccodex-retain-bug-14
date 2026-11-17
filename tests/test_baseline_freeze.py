"""基准日冻结、同源年龄与并发回灌防护的验收测试。

覆盖三个页面数据面（裁决卡片 / 扫描队列 / 分区列表）以及：
- 开单快照与裁决年龄必须同源于调用方基准日，墙钟不得顶替；
- 补采/补跑并发写必须被串行化，缺锁会导致同一分区双成功推两次；
- 本机库重算结果与页面展示均绑定基准日。
"""
import concurrent.futures

from app.db import get_db, init_db


BASELINE = "2026-11-16"
WALL_DAY = "2026-11-17"  # 比基准日晚一天，专门用来证明墙钟未顶替


def _open_judgments(authed):
    return authed.get("/api/judgments", params={"status": "待执行"}).json()["items"]


def test_scan_snapshot_freezes_caller_baseline_not_wall_clock(authed):
    scan = authed.post("/api/scan-jobs", json={"as_of_date": BASELINE})
    assert scan.status_code == 200
    job = scan.json()["job"]
    # 队列详情里的基准日必须等于调用方基准日，而不是 date.today() 墙钟
    assert job["as_of_date"] == BASELINE
    assert job["as_of_date"] != WALL_DAY

    jobs = authed.get("/api/scan-jobs").json()["items"]
    queued = next(j for j in jobs if j["id"] == job["id"])
    assert queued["as_of_date"] == BASELINE
    # 提交墙钟单独成列，与冻结基准日分列
    assert queued["created_at"]


def test_age_uses_frozen_baseline_undue_partition_excluded(authed):
    authed.post("/api/scan-jobs", json={"as_of_date": BASELINE})
    items = authed.get("/api/judgments").json()["items"]

    # orders/2026-11-10 在基准日 11-16 仅 6 天 < 保留 7 天，不得进列表
    swept = {(j["domain_code"], j["biz_date"]) for j in items}
    assert ("orders", "2026-11-10") not in swept
    # 满 7 天的 11-05、11-01 到期，保留边界正确
    assert ("orders", "2026-11-05") in swept

    # 裁决卡片：年龄按开单基准日同源计算
    card = next(
        j for j in items if (j["domain_code"], j["biz_date"]) == ("orders", "2026-11-05")
    )
    assert card["scan_as_of"] == BASELINE
    assert card["age_days"] == 11  # 11-16 - 11-05
    assert card["age_days"] >= card["keep_days"]


def test_partition_list_age_and_due_state_bound_to_baseline(authed):
    rows = authed.get(
        "/api/partitions", params={"as_of_date": BASELINE}
    ).json()["items"]
    by_key = {(r["domain_code"], r["biz_date"]): r for r in rows}

    undue = by_key[("orders", "2026-11-10")]  # 年龄 6 < 7
    assert undue["age_days"] == 6
    assert undue["due_for_expire"] is False

    due = by_key[("orders", "2026-11-05")]  # 年龄 11 >= 7
    assert due["age_days"] == 11
    assert due["due_for_expire"] is True

    # 换到更早的基准日，同一分区的到期结论随之改变（证明绑定基准日而非墙钟）
    early = authed.get(
        "/api/partitions", params={"as_of_date": "2026-11-08"}
    ).json()["items"]
    early_orders_05 = next(
        r for r in early if (r["domain_code"], r["biz_date"]) == ("orders", "2026-11-05")
    )
    assert early_orders_05["age_days"] == 3
    assert early_orders_05["due_for_expire"] is False


def test_invalid_baseline_date_rejected_400(authed):
    r = authed.post("/api/scan-jobs", json={"as_of_date": "not-a-date"})
    assert r.status_code == 400
    r2 = authed.post("/api/reconcile-reports", json={"as_of_date": "2026/11/16"})
    assert r2.status_code == 400
    r3 = authed.get("/api/partitions", params={"as_of_date": "bad"})
    assert r3.status_code == 400


def test_concurrent_scan_backfill_does_not_duplicate_open_judgments(authed):
    def fire(_):
        return authed.post("/api/scan-jobs", json={"as_of_date": BASELINE}).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        first_codes = list(pool.map(fire, range(8)))
    assert all(c == 200 for c in first_codes)

    after_first = _open_judgments(authed)
    # 基准日下应有 7 个到期分区，且每个分区恰好一张未完成裁决（无重复）
    assert len(after_first) == 7
    keys = [(j["domain_code"], j["biz_date"]) for j in after_first]
    assert len(keys) == len(set(keys))

    # 再并发补跑一轮：缺锁时墙钟侧会双成功推两次，这里数量必须纹丝不动
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        second_codes = list(pool.map(fire, range(8)))
    assert all(c == 200 for c in second_codes)
    assert len(_open_judgments(authed)) == 7


def test_unique_index_exists_on_local_database(tmp_path):
    db = tmp_path / "idx.db"
    init_db(str(db))
    with get_db(str(db)) as conn:
        indexes = {
            r["name"]
            for r in conn.execute("PRAGMA index_list('judgments')").fetchall()
        }
    assert "idx_judgments_open_partition" in indexes


def test_concurrent_execute_same_judgment_only_one_succeeds(authed):
    authed.post("/api/scan-jobs", json={"as_of_date": BASELINE})
    jid = _open_judgments(authed)[0]["id"]

    def execute(_):
        return authed.post(f"/api/judgments/{jid}/execute").status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        codes = list(pool.map(execute, range(4)))

    assert codes.count(200) == 1
    assert 409 in codes
