"""测试统一响应模块"""

import pytest

from hermes.core.response import paginated, success


class TestSuccess:
    """success() 函数测试"""

    def test_success_without_data(self):
        result = success()
        assert result["code"] == 0
        assert result["message"] == "success"
        assert "data" not in result

    def test_success_with_data_dict(self):
        result = success({"key": "value"})
        assert result["code"] == 0
        assert result["data"] == {"key": "value"}

    def test_success_with_data_list(self):
        result = success([1, 2, 3])
        assert result["code"] == 0
        assert result["data"] == [1, 2, 3]

    def test_success_with_custom_message(self):
        result = success({"id": 1}, message="创建成功")
        assert result["code"] == 0
        assert result["message"] == "创建成功"
        assert result["data"] == {"id": 1}

    def test_success_with_none_data(self):
        result = success(None)
        assert result["code"] == 0
        assert result["message"] == "success"
        assert "data" not in result

    def test_success_with_empty_string_data(self):
        result = success("")
        assert result["code"] == 0
        assert result["data"] == ""


class TestPaginated:
    """paginated() 函数测试"""

    def test_paginated_basic(self):
        items = [{"id": 1}, {"id": 2}]
        result = paginated(items, total=2, page=1, page_size=20)
        assert result["code"] == 0
        assert result["message"] == "success"
        assert result["data"]["items"] == items
        assert result["data"]["total"] == 2
        assert result["data"]["page"] == 1
        assert result["data"]["page_size"] == 20

    def test_paginated_defaults(self):
        result = paginated([], total=0)
        assert result["data"]["page"] == 1
        assert result["data"]["page_size"] == 20
        assert result["data"]["items"] == []
        assert result["data"]["total"] == 0

    def test_paginated_custom_page(self):
        result = paginated(["a", "b", "c"], total=100, page=5, page_size=10)
        assert result["data"]["page"] == 5
        assert result["data"]["page_size"] == 10
        assert result["data"]["total"] == 100
        assert len(result["data"]["items"]) == 3
