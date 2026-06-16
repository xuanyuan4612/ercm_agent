"""集成测试：案件管理 API

需要测试数据库可用（设置 TEST_DB_AVAILABLE=1 环境变量）。
"""

from __future__ import annotations

import uuid


class TestCreateCase:
    """POST /api/v1/cases"""

    async def test_create_case_success(self, client, auth_headers):
        resp = await client.post("/api/v1/cases", json={
            "fraud_source": "manual",
            "client": "ecovacs",
            "fraud_event_detail": "测试舞弊事件",
        }, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["client"] == "ecovacs"
        assert data["data"]["status"] == "pending"
        assert "task_id" in data["data"]

    async def test_create_case_cross_client_rejected(self, client, auth_headers):
        """ecovacs 用户不能创建 tineco 的案件"""
        resp = await client.post("/api/v1/cases", json={
            "fraud_source": "manual",
            "client": "tineco",
        }, headers=auth_headers)
        assert resp.status_code == 403

    async def test_create_case_missing_required(self, client, auth_headers):
        resp = await client.post("/api/v1/cases", json={
            "fraud_source": "manual",
        }, headers=auth_headers)
        assert resp.status_code == 422

    async def test_create_case_without_auth(self, client):
        resp = await client.post("/api/v1/cases", json={
            "fraud_source": "manual",
            "client": "ecovacs",
        })
        assert resp.status_code == 401

    async def test_create_case_with_group_role(self, client, group_auth_headers):
        """集团管理员应该可以创建任何事业部案件"""
        resp = await client.post("/api/v1/cases", json={
            "fraud_source": "manual",
            "client": "tineco",
        }, headers=group_auth_headers)
        assert resp.status_code == 201
        assert resp.json()["data"]["client"] == "tineco"

    async def test_create_case_with_all_fields(self, client, auth_headers):
        resp = await client.post("/api/v1/cases", json={
            "fraud_source": "phone",
            "client": "ecovacs",
            "fraud_event_detail": "详细舞弊描述",
            "proof": "证据内容",
            "attachments": ["/files/1.pdf", "/files/2.jpg"],
            "reported_staff_names": ["张三", "李四"],
            "fraud_tel": "13812345678",
            "fraud_email": "report@test.com",
            "risk_control_case_id": "RC-2024-001",
        }, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["fraud_source"] == "phone"


class TestListCases:
    """GET /api/v1/cases"""

    async def test_list_cases_empty(self, client, auth_headers):
        resp = await client.get("/api/v1/cases", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["total"] == 0
        assert data["data"]["items"] == []

    async def test_list_cases_with_data(self, client, auth_headers):
        await client.post("/api/v1/cases", json={
            "fraud_source": "manual",
            "client": "ecovacs",
            "fraud_event_detail": "案件1",
        }, headers=auth_headers)

        resp = await client.get("/api/v1/cases", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] >= 1
        assert len(data["data"]["items"]) >= 1

    async def test_list_cases_pagination(self, client, auth_headers):
        resp = await client.get("/api/v1/cases", params={
            "page": 1,
            "page_size": 5,
        }, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["page"] == 1
        assert data["data"]["page_size"] == 5

    async def test_list_cases_filter_by_client(self, client, auth_headers):
        resp = await client.get("/api/v1/cases", params={
            "client": "ecovacs",
        }, headers=auth_headers)
        assert resp.status_code == 200

    async def test_list_cases_filter_by_status(self, client, auth_headers):
        await client.post("/api/v1/cases", json={
            "fraud_source": "manual",
            "client": "ecovacs",
        }, headers=auth_headers)

        resp = await client.get("/api/v1/cases", params={
            "status": "pending",
        }, headers=auth_headers)
        assert resp.status_code == 200


class TestGetCase:
    """GET /api/v1/cases/{case_id}"""

    async def test_get_case_success(self, client, auth_headers):
        create_resp = await client.post("/api/v1/cases", json={
            "fraud_source": "manual",
            "client": "ecovacs",
            "fraud_event_detail": "详情",
        }, headers=auth_headers)
        case_id = create_resp.json()["data"]["id"]

        resp = await client.get(f"/api/v1/cases/{case_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["id"] == case_id
        assert data["data"]["fraud_event_detail"] == "详情"

    async def test_get_case_not_found(self, client, auth_headers):
        resp = await client.get(f"/api/v1/cases/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404


class TestUpdateCase:
    """PUT /api/v1/cases/{case_id}"""

    async def test_update_pending_case(self, client, auth_headers):
        create_resp = await client.post("/api/v1/cases", json={
            "fraud_source": "manual",
            "client": "ecovacs",
            "fraud_event_detail": "原始详情",
        }, headers=auth_headers)
        case_id = create_resp.json()["data"]["id"]

        resp = await client.put(f"/api/v1/cases/{case_id}", json={
            "fraud_event_detail": "更新后的详情",
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["fraud_event_detail"] == "更新后的详情"


class TestDeleteCase:
    """DELETE /api/v1/cases/{case_id}"""

    async def test_delete_pending_case(self, client, auth_headers):
        create_resp = await client.post("/api/v1/cases", json={
            "fraud_source": "manual",
            "client": "ecovacs",
        }, headers=auth_headers)
        case_id = create_resp.json()["data"]["id"]

        resp = await client.delete(f"/api/v1/cases/{case_id}", headers=auth_headers)
        assert resp.status_code == 200

        # 确认已软删除
        get_resp = await client.get(f"/api/v1/cases/{case_id}", headers=auth_headers)
        assert get_resp.status_code == 404

    async def test_delete_nonexistent_case(self, client, auth_headers):
        resp = await client.delete(f"/api/v1/cases/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404
