def test_scan_judge_execute_reconcile_chain(authed):
    # 基准日够晚，订单 7 天、事件 3 天等会产出到期裁决
    scan = authed.post("/api/scan-jobs", json={"as_of_date": "2026-11-16"})
    assert scan.status_code == 200
    job = scan.json()["job"]
    assert job["status"] == "已完成"
    assert job["expired_count"] >= 1

    pending = authed.get("/api/judgments", params={"status": "待执行"}).json()["items"]
    assert pending, "应有待执行裁决"
    first = pending[0]

    exe = authed.post(f"/api/judgments/{first['id']}/execute")
    assert exe.status_code == 200
    run = exe.json()["run"]
    assert run["ok"] == 1
    assert run["result_state"] in ("已归档", "已销毁")

    # 再执行同一条应 409
    again = authed.post(f"/api/judgments/{first['id']}/execute")
    assert again.status_code == 409

    report = authed.post(
        "/api/reconcile-reports", json={"as_of_date": "2026-11-16"}
    ).json()["report"]
    assert "在线" in report["summary"]
    assert report["mismatch_count"] == 0


def test_scan_does_not_duplicate_open_judgments(authed):
    authed.post("/api/scan-jobs", json={"as_of_date": "2026-11-16"})
    first = authed.get("/api/judgments", params={"status": "待执行"}).json()["items"]
    n1 = len(first)
    authed.post("/api/scan-jobs", json={"as_of_date": "2026-11-16"})
    second = authed.get("/api/judgments", params={"status": "待执行"}).json()["items"]
    assert len(second) == n1
