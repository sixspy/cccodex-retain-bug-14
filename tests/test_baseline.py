def test_login_page_has_password_hint(client):
    r = client.get("/login")
    assert r.status_code == 200
    text = r.text
    assert "登录" in text or "账号" in text
    assert "密码" in text


def test_login_and_meta(authed):
    r = authed.get("/api/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["lab_code"] == "cc-retain-lab"
    assert "留存" in body["lab_name"]


def test_seed_policies_and_partitions(authed):
    policies = authed.get("/api/policies").json()["items"]
    parts = authed.get("/api/partitions").json()["items"]
    assert len(policies) >= 4
    assert len(parts) >= 10
    assert all(p["active"] == 1 for p in policies)
