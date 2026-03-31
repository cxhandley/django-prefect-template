"""
Unit tests for core/mixins.py:
  - get_filtered_queryset
  - build_active_filters
  - build_table_config_json
  - build_filter_query_string
"""

import json

import pytest
from apps.core.mixins import (
    build_active_filters,
    build_filter_query_string,
    build_table_config_json,
    get_filtered_queryset,
)
from django.test import RequestFactory

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

factory = RequestFactory()

FILTER_FIELDS = {
    "status": {"type": "choice", "orm_field": "status"},
    "flow_name": {"type": "text", "orm_field": "flow_name"},
    "created_at": {"type": "datetime", "orm_field": "created_at"},
}

TABLE_COLUMNS = [
    {"key": "created_at", "label": "Date", "sortable": True, "sort_field": "created_at"},
    {"key": "status", "label": "Status", "sortable": True, "sort_field": "status"},
]


def _req(params=""):
    return factory.get(f"/flows/history/?{params}")


# ---------------------------------------------------------------------------
# build_active_filters
# ---------------------------------------------------------------------------


class TestBuildActiveFilters:
    def test_empty_request(self):
        req = _req()
        assert build_active_filters(req) == []

    def test_single_filter(self):
        req = _req("f_field[]=status&f_op[]=eq&f_val[]=COMPLETED")
        result = build_active_filters(req)
        assert result == [{"field": "status", "op": "eq", "value": "COMPLETED"}]

    def test_multiple_filters(self):
        req = _req(
            "f_field[]=status&f_op[]=eq&f_val[]=COMPLETED"
            "&f_field[]=flow_name&f_op[]=contains&f_val[]=credit"
        )
        result = build_active_filters(req)
        assert len(result) == 2
        assert result[0] == {"field": "status", "op": "eq", "value": "COMPLETED"}
        assert result[1] == {"field": "flow_name", "op": "contains", "value": "credit"}

    def test_skips_incomplete_rows(self):
        # Missing op → not included
        req = _req("f_field[]=status&f_op[]=&f_val[]=COMPLETED")
        result = build_active_filters(req)
        assert result == []


# ---------------------------------------------------------------------------
# build_filter_query_string
# ---------------------------------------------------------------------------


class TestBuildFilterQueryString:
    def test_removes_page_param(self):
        req = _req("f_field[]=status&f_op[]=eq&f_val[]=COMPLETED&page=3")
        qs = build_filter_query_string(req)
        assert "page" not in qs
        assert "f_field" in qs

    def test_empty_request(self):
        req = _req()
        assert build_filter_query_string(req) == ""

    def test_preserves_sort(self):
        req = _req("sort=-created_at&page=2")
        qs = build_filter_query_string(req)
        assert "sort=-created_at" in qs
        assert "page" not in qs


# ---------------------------------------------------------------------------
# build_table_config_json
# ---------------------------------------------------------------------------


class TestBuildTableConfigJson:
    def _minimal_config(self, **extra):
        cfg = {
            "table_id": "history",
            "hx_url": "/flows/history/",
            "hx_target": "#dt-history-body",
            "columns": [],
            "bulk_actions": [],
            "active_filters": [],
            "sort_field": "-created_at",
        }
        cfg.update(extra)
        return cfg

    def test_returns_valid_json(self):
        cfg = self._minimal_config()
        result = build_table_config_json(cfg)
        parsed = json.loads(result)
        assert parsed["tableId"] == "history"
        assert parsed["hxUrl"] == "/flows/history/"

    def test_camelcase_keys(self):
        cfg = self._minimal_config()
        parsed = json.loads(build_table_config_json(cfg))
        assert "tableId" in parsed
        assert "hxUrl" in parsed
        assert "hxTarget" in parsed
        assert "sortField" in parsed
        assert "activeFilters" in parsed
        assert "fieldConfigs" in parsed
        assert "bulkActions" in parsed

    def test_filterable_columns_become_field_configs(self):
        cfg = self._minimal_config(
            columns=[
                {
                    "key": "status",
                    "label": "Status",
                    "filterable": True,
                    "filter_type": "choice",
                    "filter_choices": [{"value": "COMPLETED", "label": "Completed"}],
                }
            ]
        )
        parsed = json.loads(build_table_config_json(cfg))
        assert "status" in parsed["fieldConfigs"]
        assert parsed["fieldConfigs"]["status"]["type"] == "choice"
        assert parsed["fieldConfigs"]["status"]["label"] == "Status"

    def test_non_filterable_columns_excluded_from_field_configs(self):
        cfg = self._minimal_config(
            columns=[{"key": "created_at", "label": "Date", "filterable": False}]
        )
        parsed = json.loads(build_table_config_json(cfg))
        assert "created_at" not in parsed["fieldConfigs"]

    def test_bulk_actions_serialised_correctly(self):
        cfg = self._minimal_config(
            bulk_actions=[
                {
                    "key": "compare",
                    "label": "Compare",
                    "method": "GET",
                    "url": "/flows/comparison/",
                    "id_param": "ids",
                    "id_sep": ",",
                    "min_select": 2,
                    "max_select": 3,
                    "confirm": False,
                }
            ]
        )
        parsed = json.loads(build_table_config_json(cfg))
        action = parsed["bulkActions"][0]
        assert action["key"] == "compare"
        assert action["minSelect"] == 2
        assert action["maxSelect"] == 3
        assert action["idParam"] == "ids"

    def test_max_select_none_becomes_json_null(self):
        cfg = self._minimal_config(
            bulk_actions=[
                {
                    "key": "delete",
                    "label": "Delete",
                    "method": "POST",
                    "url": "/delete/",
                    "max_select": None,
                }
            ]
        )
        parsed = json.loads(build_table_config_json(cfg))
        assert parsed["bulkActions"][0]["maxSelect"] is None


# ---------------------------------------------------------------------------
# get_filtered_queryset
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetFilteredQueryset:
    def _qs(self):
        from apps.flows.models import FlowExecution

        return FlowExecution.objects.all()

    def test_no_filters_returns_full_queryset(self, user, flow_execution_factory):
        flow_execution_factory(triggered_by=user, status="COMPLETED")
        flow_execution_factory(triggered_by=user, status="FAILED")
        req = _req()
        qs, _ = get_filtered_queryset(req, self._qs(), FILTER_FIELDS, TABLE_COLUMNS)
        assert qs.count() == 2

    def test_single_choice_filter(self, user, flow_execution_factory):
        flow_execution_factory(triggered_by=user, status="COMPLETED")
        flow_execution_factory(triggered_by=user, status="FAILED")
        req = _req("f_field[]=status&f_op[]=eq&f_val[]=COMPLETED")
        qs, _ = get_filtered_queryset(req, self._qs(), FILTER_FIELDS, TABLE_COLUMNS)
        assert qs.count() == 1
        assert qs.first().status == "COMPLETED"

    def test_unknown_field_ignored(self, user, flow_execution_factory):
        flow_execution_factory(triggered_by=user, status="COMPLETED")
        req = _req("f_field[]=nonexistent&f_op[]=eq&f_val[]=foo")
        qs, _ = get_filtered_queryset(req, self._qs(), FILTER_FIELDS, TABLE_COLUMNS)
        assert qs.count() == 1

    def test_valid_sort_applied(self, user, flow_execution_factory):
        flow_execution_factory(triggered_by=user, flow_name="aaa")
        flow_execution_factory(triggered_by=user, flow_name="zzz")
        req = _req("sort=status")
        qs, sort = get_filtered_queryset(req, self._qs(), FILTER_FIELDS, TABLE_COLUMNS)
        assert sort == "status"
        assert qs.count() == 2

    def test_invalid_sort_falls_back_to_default(self, user, flow_execution_factory):
        flow_execution_factory(triggered_by=user)
        req = _req("sort=__evil__injection")
        qs, sort = get_filtered_queryset(
            req, self._qs(), FILTER_FIELDS, TABLE_COLUMNS, default_sort="-created_at"
        )
        assert sort == "-created_at"

    def test_filter_with_empty_val_skipped_for_non_empty_ops(self, user, flow_execution_factory):
        flow_execution_factory(triggered_by=user, status="COMPLETED")
        flow_execution_factory(triggered_by=user, status="FAILED")
        # op eq with blank value — should be skipped
        req = _req("f_field[]=status&f_op[]=eq&f_val[]=")
        qs, _ = get_filtered_queryset(req, self._qs(), FILTER_FIELDS, TABLE_COLUMNS)
        assert qs.count() == 2
